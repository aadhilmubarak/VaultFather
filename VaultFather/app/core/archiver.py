"""
The archiving engine — wraps the local 7z executable to produce a
password-protected, header-encrypted .7z archive from a movie file,
reporting live progress as it goes.

Why shell out to 7z.exe instead of a pure-Python library (py7zr etc.):
real 7-Zip is faster on large files, supports -mhe=on (encrypts file
names too, not just contents), and is what VaultFather asks the person
to already have installed — no bundling, no licensing questions.
"""

import glob
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_seven_zip_path, COMPRESSION_LEVELS

_PROGRESS_RE = re.compile(r"(\d{1,3})%")


class SevenZipNotFoundError(RuntimeError):
    """Raised when no usable 7z executable can be located."""


@dataclass
class ArchiveResult:
    success: bool
    archive_volumes: list[str] = field(default_factory=list)  # one path, or many if split
    error_message: str | None = None

    @property
    def archive_path(self) -> str | None:
        """First volume — convenient when the archive wasn't split."""
        return self.archive_volumes[0] if self.archive_volumes else None

    @property
    def is_split(self) -> bool:
        return len(self.archive_volumes) > 1


def build_archive_path(source_path: str, output_dir: str | None = None) -> str:
    """
    Chooses where the .7z lands: the configured output dir if set,
    otherwise right next to the source movie.
    """
    source = Path(source_path)
    target_dir = Path(output_dir) if output_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / f"{source.stem}.7z")


def archive_movie(
    source_path: str,
    password: str,
    output_dir: str | None = None,
    compression_level: str = "store",
    split_volume_size_mb: int | None = None,
    progress_callback=None,
    cancel_event: threading.Event | None = None,
    subtitle_paths: list[str] | None = None,
) -> ArchiveResult:
    """
    Archives a single movie file into a password-protected .7z — split
    into fixed-size volumes if split_volume_size_mb is set, which is the
    key move for Telegram: it caps every individual upload well under
    Telegram's per-file limit, and turns "resume a failed upload" into
    "resume from the last complete volume" instead of "start the whole
    movie over".

    subtitle_paths, if given, are inserted into the archive BEFORE the
    movie file. 7-Zip processes inputs in order so the small subtitle
    files land intact in the first part — they are never split across
    volumes. Only the movie itself gets chunked.

    progress_callback, if given, is called with an int 0-100 as 7z
    reports progress across the whole job (all volumes combined) — it's
    called from whatever thread this function runs on; the caller is
    responsible for marshalling back to the UI thread before touching
    any widgets.

    cancel_event, if given, is checked periodically; setting it will
    terminate the 7z process and return a failed ArchiveResult rather
    than raising.
    """
    seven_zip = get_seven_zip_path()
    if not seven_zip:
        return ArchiveResult(
            success=False,
            error_message=(
                "Couldn't find 7-Zip. Make sure it's installed, or set its "
                "path in Settings."
            ),
        )

    if not Path(source_path).is_file():
        return ArchiveResult(success=False, error_message=f"File not found: {source_path}")

    # Validate subtitle paths — silently drop any that have gone missing
    valid_subtitles: list[str] = [
        p for p in (subtitle_paths or []) if Path(p).is_file()
    ]

    archive_path = build_archive_path(source_path, output_dir)
    _clear_existing_volumes(archive_path)
    mx = COMPRESSION_LEVELS.get(compression_level, "0")

    command = [
        seven_zip, "a", "-t7z",
        f"-p{password}",
        "-mhe=on",       # encrypt file names too, not just contents
        f"-mx={mx}",
        "-bsp1",         # emit progress to stdout
        "-y",            # assume yes to any prompt
    ]
    if split_volume_size_mb:
        command.append(f"-v{int(split_volume_size_mb)}m")
    # Subtitles first (land in part 1, never split), then movie
    command.append(archive_path)
    command.extend(valid_subtitles)
    command.append(source_path)


    import sys
    _popen_kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if sys.platform.startswith("win"):
        _popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        process = subprocess.Popen(command, **_popen_kwargs)
    except OSError as exc:
        return ArchiveResult(success=False, error_message=f"Couldn't start 7-Zip: {exc}")

    output_tail = []
    last_percent = -1

    while True:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            process.wait(timeout=5)
            return ArchiveResult(success=False, error_message="Cancelled.")

        chunk = process.stdout.read(256)
        if not chunk:
            if process.poll() is not None:
                break
            continue

        output_tail.append(chunk)
        output_tail[:] = output_tail[-20:]  # keep only the tail, for error messages

        matches = _PROGRESS_RE.findall(chunk)
        if matches and progress_callback:
            percent = int(matches[-1])
            if percent != last_percent:
                last_percent = percent
                progress_callback(percent)

    process.wait()

    if process.returncode == 0:
        if progress_callback and last_percent != 100:
            progress_callback(100)
        volumes = _resolve_output_volumes(archive_path)
        return ArchiveResult(success=True, archive_volumes=volumes)

    error_text = "".join(output_tail).strip().splitlines()
    error_summary = error_text[-1] if error_text else "Unknown 7-Zip error."
    return ArchiveResult(success=False, error_message=error_summary)


def _clear_existing_volumes(archive_path: str) -> None:
    """
    7-Zip can fail oddly (E_NOTIMPL) if it finds leftover volumes from a
    previous run at the same path — e.g. a retry after an interrupted
    archive. Since we're about to create a fresh archive from scratch
    (not appending to one), it's safe to clear the way first.
    """
    stale = [archive_path, *glob.glob(f"{archive_path}.*")]
    for path in stale:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def _resolve_output_volumes(archive_path: str) -> list[str]:
    """
    When splitting is on, 7z writes archive.7z.001, .002, ... instead of
    a plain archive.7z. Figure out which actually landed on disk.
    """
    if Path(archive_path).is_file():
        return [archive_path]

    volume_candidates = sorted(glob.glob(f"{archive_path}.*"))
    return volume_candidates
