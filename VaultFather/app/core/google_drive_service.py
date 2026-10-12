"""
Google Drive backup: exports the backup history to Excel and uploads it
to a "VaultFather Backups" folder in the connected Google account's
Drive, overwriting the previous day's file each time (so Drive doesn't
fill up with one file per day forever).

Uses the standard OAuth "installed app" loopback flow — the same
pattern every desktop app that connects to a Google account uses:
opens the person's browser to Google's consent screen, catches the
redirect on a local port, and never touches the person's Google
password directly. The resulting token is refreshed automatically by
the google-auth library and cached locally, so this is a one-time
connect, not a re-login every day.

Requires a one-time Google Cloud Console setup (Client ID + Client
Secret) — there's no way around this, Google requires every app to
register itself before it can request access to anyone's Drive.
"""

import io
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.core.config import load_config, save_config

TOKEN_PATH = Path.home() / ".vaultfather" / "google_token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BACKUP_FOLDER_NAME = "VaultFather Backups"
BACKUP_FILENAME = "VaultFather Backup History.xlsx"


class GoogleNotConfiguredError(RuntimeError):
    pass


class GoogleNotConnectedError(RuntimeError):
    pass


def has_client_credentials() -> bool:
    config = load_config()
    return bool(config.get("google_client_id") and config.get("google_client_secret"))


def has_saved_token() -> bool:
    return TOKEN_PATH.is_file()


def _client_config() -> dict:
    config = load_config()
    client_id = config.get("google_client_id")
    client_secret = config.get("google_client_secret")
    if not client_id or not client_secret:
        raise GoogleNotConfiguredError(
            "Google isn't set up yet — add your Client ID and Client Secret in Settings."
        )
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def run_oauth_login() -> str:
    """
    Blocking — opens the browser, waits for the person to sign in and
    consent, then saves the token to disk. Meant to be called from a
    background thread, never the UI thread. Returns the connected
    account's email address.
    """
    flow = InstalledAppFlow.from_client_config(_client_config(), DRIVE_SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True)

    # Fetch email via Drive's about.get() — covered by drive.file scope.
    # Done BEFORE saving the token so a bad token is never left on disk.
    drive_service = build("drive", "v3", credentials=credentials)
    about = drive_service.about().get(fields="user").execute()
    email = about.get("user", {}).get("emailAddress", "")

    # Everything succeeded — persist token and config.
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(credentials.to_json())

    config = load_config()
    config["google_drive_connected_email"] = email
    save_config(config)
    return email


def disconnect() -> None:
    if TOKEN_PATH.is_file():
        TOKEN_PATH.unlink()
    config = load_config()
    config["google_drive_connected_email"] = None
    save_config(config)


def _load_credentials() -> Credentials:
    if not TOKEN_PATH.is_file():
        raise GoogleNotConnectedError("Google Drive isn't connected — connect it in Settings.")

    credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), DRIVE_SCOPES)
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            TOKEN_PATH.write_text(credentials.to_json())
        except Exception as exc:
            # Google revoked the token (e.g. password changed, app access removed,
            # or the OAuth client was re-configured). The saved token is now useless —
            # delete it and surface a clear "reconnect" error instead of a raw crash.
            err_str = str(exc).lower()
            if "invalid_grant" in err_str or "token has been expired or revoked" in err_str:
                TOKEN_PATH.unlink(missing_ok=True)
                config = load_config()
                config["google_drive_connected_email"] = None
                save_config(config)
                raise GoogleNotConnectedError(
                    "Google Drive token was revoked or expired. "
                    "Please reconnect your Google account in Settings."
                ) from exc
            raise
    return credentials


def _find_or_create_folder(drive_service) -> str:
    query = (
        f"name='{BACKUP_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    folder = drive_service.files().create(
        body={"name": BACKUP_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]


def upload_backup_file(local_path: str) -> None:
    """
    Uploads local_path to the VaultFather Backups folder in Drive,
    overwriting any previous file with the same name rather than
    piling up a new file every day.
    """
    credentials = _load_credentials()
    drive_service = build("drive", "v3", credentials=credentials)

    folder_id = _find_or_create_folder(drive_service)

    query = f"name='{BACKUP_FILENAME}' and '{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    existing = results.get("files", [])

    media = MediaFileUpload(
        local_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if existing:
        drive_service.files().update(fileId=existing[0]["id"], media_body=media).execute()
    else:
        drive_service.files().create(
            body={"name": BACKUP_FILENAME, "parents": [folder_id]},
            media_body=media,
        ).execute()
