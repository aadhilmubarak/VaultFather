"""
System Default Media Player & VLC Launcher.

Supports launching movies with multiple candidate subtitle tracks in VLC
for real-time preview and synchronization inspection.
"""

import os
import shutil
import subprocess
import sys


def find_vlc_path() -> str | None:
    """Finds the VLC media player binary on the system."""
    on_path = shutil.which("vlc") or shutil.which("vlc.exe")
    if on_path and os.path.isfile(on_path):
        return on_path

    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    elif sys.platform == "darwin":
        mac_vlc = "/Applications/VLC.app/Contents/MacOS/VLC"
        if os.path.isfile(mac_vlc):
            return mac_vlc

    return None


def play_movie(movie_path: str, start_seconds: float | None = None, audio_track: int | None = None) -> None:
    """
    Opens the movie file in VLC if available, or the system's default media player
    (MPC-HC, MPV, PotPlayer, Windows Media Player, etc.).
    Note: VLC is strongly preferred across VaultFather for rich playback tracking
    and multi-subtitle track loading.
    """
    abs_path = os.path.normpath(os.path.abspath(movie_path))
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Movie file not found: {abs_path}")

    try:
        from app.core.database import get_playback_position, save_playback_position
        pos, dur, at = get_playback_position(abs_path)
        save_playback_position(abs_path, pos, dur, at)
    except Exception:
        pass

    vlc = find_vlc_path()
    if vlc and os.path.isfile(vlc):
        args = [vlc, abs_path]
        if start_seconds and start_seconds > 0:
            args.append(f"--start-time={int(start_seconds)}")
        subprocess.Popen(args)
    elif sys.platform.startswith("win"):
        os.startfile(abs_path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", abs_path])
    else:
        subprocess.Popen(["xdg-open", abs_path])


# Alias for backward compatibility
play_in_vlc = play_movie


def launch_vlc_with_subtitles(movie_path: str, subtitle_paths: list[str]) -> bool:
    """
    Launches video with candidate subtitle tracks.
    If VLC is available, loads all subtitles simultaneously via --sub-file and --input-slave
    so the user can switch tracks on the fly.
    If VLC is not available, falls back to the system default media player with the first subtitle.
    Returns True if VLC was used, False if system default player fallback was used.
    """
    abs_movie = os.path.normpath(os.path.abspath(movie_path))
    if not os.path.isfile(abs_movie):
        raise FileNotFoundError(f"Movie file not found: {abs_movie}")

    vlc = find_vlc_path()
    valid_subs = [os.path.normpath(os.path.abspath(s)) for s in subtitle_paths if os.path.isfile(s)]

    if vlc and os.path.isfile(vlc):
        args = [vlc, abs_movie]
        if valid_subs:
            args.append(f"--sub-file={valid_subs[0]}")
            for slave_sub in valid_subs[1:]:
                args.append(f"--input-slave={slave_sub}")
        subprocess.Popen(args)
        return True
    else:
        if sys.platform.startswith("win"):
            os.startfile(abs_movie)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", abs_movie])
        else:
            subprocess.Popen(["xdg-open", abs_movie])
        return False

