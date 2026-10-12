"""
Embedded VLC Video Player — Cyber Obsidian Glass HUD overlay.

Uses the PC's locally installed VLC (libvlc.dll) via python-vlc bindings.
No VLC binaries are copied into VaultFather.

Features & VLC Functions:
  • Multi-Audio Track Switching (Internal / Dual Audio / Commentary)
  • Subtitle Track Switching (Embedded MKV/MP4 subs + External SRT/ASS)
  • Subtitle Sync / Delay Adjustment (audio_set_delay / spu_set_delay)
  • Audio Delay Adjustment
  • Playback Speed Control (0.25x - 3.0x)
  • Aspect Ratio Modes (Original/Fit, 16:9, 4:3, 21:9, 16:10)
  • Volume Amplification (Up to 200%) & Mute Toggle
  • Frame Stepping (Next Frame) & Video Snapshot (Screenshot)
  • Context Menu (Right-Click on Video Surface)
  • Keyboard Shortcuts (Space, F, M, S, E, A, V, Arrows, Esc)
  • Automatic Playback Position Saving & Resume
"""

import os
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QSizePolicy, QApplication, QMessageBox,
    QMenu, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QPoint
from PySide6.QtGui import QKeyEvent, QMouseEvent, QAction

# ── Dynamic VLC DLL Discovery ────────────────────────────────────────────────
def _setup_vlc_dll_path():
    if not sys.platform.startswith("win"):
        return
    candidates = [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
    ]
    try:
        import winreg
        for key_path in [r"SOFTWARE\VideoLAN\VLC", r"SOFTWARE\WOW6432Node\VideoLAN\VLC"]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                    val, _ = winreg.QueryValueEx(k, "InstallDir")
                    if val and val not in candidates:
                        candidates.insert(0, val)
            except Exception:
                pass
    except Exception:
        pass

    for path in candidates:
        if os.path.exists(os.path.join(path, "libvlc.dll")):
            try:
                os.add_dll_directory(path)
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
                os.environ["VLC_PLUGIN_PATH"] = os.path.join(path, "plugins")
            except Exception:
                pass
            break

_setup_vlc_dll_path()

try:
    import vlc  # type: ignore
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False

from app.core.database import save_playback_position, get_playback_position
from app.core.subtitle_service import fetch_and_save_subtitles, get_cached_subtitle_path


def _fmt(ms: int) -> str:
    s = max(0, int(ms / 1000))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class ClickableSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            val = (
                self.minimum()
                + ((self.maximum() - self.minimum())
                   * event.position().x()) / max(1, self.width())
            )
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


class VideoSurface(QFrame):
    """Clickable and double-clickable video container for play/pause and fullscreen."""
    clicked = Signal()
    double_clicked = Signal()
    context_menu_requested = Signal(QPoint)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._click_pos = event.position()
        elif event.button() == Qt.RightButton:
            self.context_menu_requested.emit(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and hasattr(self, "_click_pos"):
            if (event.position() - self._click_pos).manhattanLength() < 5:
                self.clicked.emit()
        super().mouseReleaseEvent(event)


class EmbeddedPlayerWidget(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmbeddedPlayer")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.movie_path: str = ""
        self.movie_title: str = ""
        self._user_is_sliding = False
        self._last_mouse_move = time.time()
        self._hwnd_bound = False
        self._is_muted = False
        self._last_volume = 80
        self._audio_delay_ms = 0
        self._sub_delay_ms = 0

        self._vlc_instance = None
        self._player = None

        self._build_ui()
        self._init_vlc()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(250)
        self._poll_timer.timeout.connect(self._on_poll)
        self._poll_timer.start()

        self._hide_timer = QTimer(self)
        self._hide_timer.setInterval(3000)
        self._hide_timer.timeout.connect(self._maybe_hide_controls)
        self._hide_timer.start()

    # ── VLC init ──────────────────────────────────────────────────────────────

    def _init_vlc(self):
        if not VLC_AVAILABLE:
            return
        try:
            self._vlc_instance = vlc.Instance([
                "--no-video-title-show",
                "--quiet",
                "--sub-filter=marq"
            ])
            self._player = self._vlc_instance.media_player_new()
        except Exception as exc:
            self._vlc_instance = None
            self._player = None
            print(f"[VLC] init failed: {exc}")

    def _bind_hwnd(self):
        if not self._player or self._hwnd_bound:
            return
        try:
            wid = int(self.video_frame.winId())
            if sys.platform.startswith("win"):
                self._player.set_hwnd(wid)
            elif sys.platform.startswith("linux"):
                self._player.set_xwindow(wid)
            elif sys.platform == "darwin":
                self._player.set_nsobject(wid)
            self._hwnd_bound = True
        except Exception as exc:
            print(f"[VLC] hwnd bind failed: {exc}")

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        QTimer.singleShot(50, self._bind_hwnd)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Video Surface Frame
        self.video_frame = VideoSurface(self)
        self.video_frame.setStyleSheet("background-color: #000000;")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_frame.clicked.connect(self.toggle_play)
        self.video_frame.double_clicked.connect(self.toggle_fullscreen)
        self.video_frame.context_menu_requested.connect(self._show_context_menu)
        root.addWidget(self.video_frame, stretch=1)

        # ── Floating Top HUD ─────────────────────────────────────────────────
        self.top_hud = QFrame(self)
        top_lay = QHBoxLayout(self.top_hud)
        top_lay.setContentsMargins(16, 8, 16, 8)

        self.back_btn = QPushButton("⤺  Back to Movies")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet(
            "background-color: rgba(0,240,255,22); color: #00F0FF;"
            "border: 1px solid rgba(0,240,255,70); border-radius: 10px;"
            "padding: 6px 14px; font-weight: 700; font-size: 12px;"
        )
        self.back_btn.clicked.connect(self.close_player)
        top_lay.addWidget(self.back_btn)

        self.title_label = QLabel("Now Playing")
        self.title_label.setStyleSheet(
            "color: #E8F4FF; font-size: 15px; font-weight: 700; margin-left: 12px;"
        )
        top_lay.addWidget(self.title_label)
        top_lay.addStretch()

        self.sub_status = QLabel("")
        self.sub_status.setStyleSheet("color: #00FFC8; font-size: 11.5px; font-weight: 600; margin-right: 12px;")
        top_lay.addWidget(self.sub_status)

        # Settings / Menu button in Top HUD
        self.menu_btn = QPushButton("⚙ Options")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setStyleSheet(
            "background: rgba(0,240,255,14); color: #E8F4FF;"
            "border: 1px solid rgba(0,240,255,35); border-radius: 8px;"
            "padding: 5px 12px; font-size: 11.5px; font-weight: 600;"
        )
        self.menu_btn.clicked.connect(lambda: self._show_context_menu(self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height()))))
        top_lay.addWidget(self.menu_btn)

        # ── Floating Bottom HUD ──────────────────────────────────────────────
        self.bottom_hud = QFrame(self)
        bot_lay = QVBoxLayout(self.bottom_hud)
        bot_lay.setContentsMargins(16, 6, 16, 12)
        bot_lay.setSpacing(6)

        # Timeline row
        tl = QHBoxLayout()
        tl.setSpacing(10)

        self.cur_lbl = QLabel("00:00")
        self.cur_lbl.setStyleSheet("color: #8BA8C8; font-size: 11px; min-width: 46px;")
        tl.addWidget(self.cur_lbl)

        self.timeline = ClickableSlider(Qt.Horizontal)
        self.timeline.setRange(0, 1000)
        self.timeline.setStyleSheet(
            "QSlider::groove:horizontal { height: 5px; background: rgba(0,240,255,30); border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #00F0FF; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #E8F4FF; border: 2px solid #00F0FF; "
            "  width: 14px; margin: -5px 0; border-radius: 7px; }"
        )
        self.timeline.sliderPressed.connect(lambda: setattr(self, "_user_is_sliding", True))
        self.timeline.sliderMoved.connect(self._on_slider_moved)
        self.timeline.sliderReleased.connect(self._on_slider_released)
        tl.addWidget(self.timeline, stretch=1)

        self.dur_lbl = QLabel("00:00")
        self.dur_lbl.setStyleSheet("color: #8BA8C8; font-size: 11px; min-width: 46px;")
        tl.addWidget(self.dur_lbl)
        bot_lay.addLayout(tl)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        # Play / Pause
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(38, 38)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #00F0FF,stop:1 #7B2FF7);"
            "color: #080714; font-size: 15px; font-weight: 700; border: none; border-radius: 19px;"
        )
        self.play_btn.clicked.connect(self.toggle_play)
        ctrl.addWidget(self.play_btn)

        # Seek 10s back / forward
        for label, delta in [("⏪ 10s", -10000), ("10s ⏩", 10000)]:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "background: rgba(0,240,255,14); color: #E8F4FF;"
                "border: 1px solid rgba(0,240,255,35); border-radius: 8px;"
                "padding: 5px 10px; font-size: 11px;"
            )
            btn.clicked.connect(lambda _, d=delta: self.seek_relative(d))
            ctrl.addWidget(btn)

        ctrl.addSpacing(8)

        # Volume icon / Mute
        self.vol_btn = QPushButton("🔊")
        self.vol_btn.setFixedSize(28, 28)
        self.vol_btn.setCursor(Qt.PointingHandCursor)
        self.vol_btn.setStyleSheet(
            "background: transparent; color: #00F0FF; font-size: 14px; border: none;"
        )
        self.vol_btn.clicked.connect(self.toggle_mute)
        ctrl.addWidget(self.vol_btn)

        # Volume slider (0 - 200%)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 200)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(88)
        self.vol_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: rgba(0,240,255,30); border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #00FFC8; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #E8F4FF; width: 10px; margin: -3px 0; border-radius: 5px; }"
        )
        self.vol_slider.valueChanged.connect(self._on_volume)
        ctrl.addWidget(self.vol_slider)

        self.vol_lbl = QLabel("80%")
        self.vol_lbl.setStyleSheet("color: #8BA8C8; font-size: 10.5px; min-width: 32px;")
        ctrl.addWidget(self.vol_lbl)

        ctrl.addStretch()

        # Audio Track selector
        self.audio_btn = QPushButton("🎵 Audio")
        self.audio_btn.setCursor(Qt.PointingHandCursor)
        self.audio_btn.setStyleSheet(
            "background: rgba(0,240,255,14); color: #E8F4FF;"
            "border: 1px solid rgba(0,240,255,35); border-radius: 8px;"
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        self.audio_btn.clicked.connect(self._show_audio_tracks_menu)
        ctrl.addWidget(self.audio_btn)

        # Subtitles button
        self.sub_menu_btn = QPushButton("💬 Subtitles")
        self.sub_menu_btn.setCursor(Qt.PointingHandCursor)
        self.sub_menu_btn.setStyleSheet(
            "background: rgba(0,255,200,18); color: #00FFC8;"
            "border: 1px solid rgba(0,255,200,55); border-radius: 8px;"
            "padding: 5px 10px; font-weight: 600; font-size: 11px;"
        )
        self.sub_menu_btn.clicked.connect(self._show_subtitles_menu)
        ctrl.addWidget(self.sub_menu_btn)

        # Speed selector button
        self.speed_btn = QPushButton("⚡ 1.0x")
        self.speed_btn.setCursor(Qt.PointingHandCursor)
        self.speed_btn.setStyleSheet(
            "background: rgba(0,240,255,14); color: #E8F4FF;"
            "border: 1px solid rgba(0,240,255,35); border-radius: 8px;"
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        self.speed_btn.clicked.connect(self._show_speed_menu)
        ctrl.addWidget(self.speed_btn)

        # Aspect Ratio button
        self.aspect_btn = QPushButton("📐 Aspect")
        self.aspect_btn.setCursor(Qt.PointingHandCursor)
        self.aspect_btn.setStyleSheet(
            "background: rgba(0,240,255,14); color: #E8F4FF;"
            "border: 1px solid rgba(0,240,255,35); border-radius: 8px;"
            "padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        self.aspect_btn.clicked.connect(self._show_aspect_menu)
        ctrl.addWidget(self.aspect_btn)

        # Snapshot button
        self.snap_btn = QPushButton("📸")
        self.snap_btn.setFixedSize(30, 30)
        self.snap_btn.setCursor(Qt.PointingHandCursor)
        self.snap_btn.setToolTip("Take Snapshot (S)")
        self.snap_btn.setStyleSheet(
            "background: rgba(0,240,255,14); color: #00F0FF;"
            "border: 1px solid rgba(0,240,255,35); border-radius: 6px;"
            "font-size: 13px;"
        )
        self.snap_btn.clicked.connect(self.take_snapshot)
        ctrl.addWidget(self.snap_btn)

        bot_lay.addLayout(ctrl)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.top_hud.setGeometry(0, 0, self.width(), 58)
        self.bottom_hud.setGeometry(0, max(0, self.height() - 95), self.width(), 95)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._last_mouse_move = time.time()
        self.top_hud.show()
        self.bottom_hud.show()
        super().mouseMoveEvent(event)

    def _maybe_hide_controls(self):
        try:
            if self._player and self._player.is_playing():
                if time.time() - self._last_mouse_move > 3.0:
                    self.top_hud.hide()
                    self.bottom_hud.hide()
        except Exception:
            pass

    # ── Playback Logic ────────────────────────────────────────────────────────

    def play_movie(self, movie_path: str, title: str):
        if not os.path.isfile(movie_path):
            QMessageBox.critical(self, "Error", f"File not found:\n{movie_path}")
            return
        from app.core.vlc_launcher import play_in_vlc
        try:
            play_in_vlc(movie_path)
        except Exception as exc:
            QMessageBox.critical(self, "Playback Error", f"Could not launch VLC player:\n{exc}")
        self.closed.emit()

        if not VLC_AVAILABLE or not self._player:
            QMessageBox.warning(self, "VLC Required",
                                "VLC is not available. Please install VLC Media Player.")
            return

        try:
            self._bind_hwnd()
            media = self._vlc_instance.media_new(str(movie_path))
            self._player.set_media(media)
            self._player.play()
            self.play_btn.setText("⏸")
            self._on_volume(self.vol_slider.value())
        except Exception as exc:
            QMessageBox.critical(self, "Playback Error", str(exc))
            return

        # Load existing cached subtitles if any
        existing_sub = get_cached_subtitle_path(movie_path)
        if existing_sub:
            self._load_sub(existing_sub)

        # Restore playback position
        saved_pos, _ = get_playback_position(movie_path)
        if saved_pos > 10.0:
            QTimer.singleShot(900, lambda: self._restore_pos(int(saved_pos * 1000)))

    def _restore_pos(self, target_ms: int):
        try:
            if self._player:
                self._player.set_time(target_ms)
                self.sub_status.setText(f"Resumed at {_fmt(target_ms)}")
                QTimer.singleShot(3000, lambda: self.sub_status.setText(""))
        except Exception:
            pass

    def _load_sub(self, srt_path: str):
        try:
            if self._player and os.path.isfile(srt_path):
                self._player.add_slave(
                    vlc.MediaSlaveType.subtitle,
                    Path(srt_path).as_uri(), True
                )
                self.sub_status.setText("✔ Subtitle Loaded")
        except Exception:
            pass

    def auto_fetch_subtitles(self):
        if not self.movie_path:
            return
        self.sub_status.setText("Searching subtitles…")

        def _fetch():
            sub = fetch_and_save_subtitles(self.movie_path)
            if sub:
                self._load_sub(sub)
                self.sub_status.setText("✔ Subtitles downloaded & synced")
            else:
                self.sub_status.setText("✖ No subtitles found")

        QTimer.singleShot(80, _fetch)

    def load_external_subtitle_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Subtitle File", "", "Subtitle Files (*.srt *.ass *.vtt *.sub)"
        )
        if path:
            self._load_sub(path)

    def toggle_play(self):
        try:
            if not self._player:
                return
            if self._player.is_playing():
                self._player.pause()
                self.play_btn.setText("▶")
                self._save_pos()
            else:
                self._player.play()
                self.play_btn.setText("⏸")
        except Exception:
            pass

    def toggle_fullscreen(self):
        window = self.window()
        if window:
            if window.isFullScreen():
                window.showMaximized()
            else:
                window.showFullScreen()

    def toggle_mute(self):
        try:
            if not self._player:
                return
            if self._is_muted:
                self._player.audio_set_mute(False)
                self._is_muted = False
                self.vol_btn.setText("🔊")
                self.vol_slider.setValue(self._last_volume)
            else:
                self._last_volume = self.vol_slider.value()
                self._player.audio_set_mute(True)
                self._is_muted = True
                self.vol_btn.setText("🔇")
                self.vol_lbl.setText("Muted")
        except Exception:
            pass

    def seek_relative(self, delta_ms: int):
        try:
            if self._player:
                cur = self._player.get_time()
                if cur >= 0:
                    self._player.set_time(max(0, cur + delta_ms))
        except Exception:
            pass

    def next_frame(self):
        try:
            if self._player:
                self._player.next_frame()
        except Exception:
            pass

    def take_snapshot(self):
        try:
            if self._player and self.movie_path:
                pics_dir = Path.home() / "Pictures" / "VaultFather Snapshots"
                pics_dir.mkdir(parents=True, exist_ok=True)
                timestamp = int(time.time())
                filename = f"snapshot_{timestamp}.png"
                filepath = str(pics_dir / filename)
                self._player.video_take_snapshot(0, filepath, 0, 0)
                self.sub_status.setText(f"📸 Saved to Pictures: {filename}")
                QTimer.singleShot(3500, lambda: self.sub_status.setText(""))
        except Exception as exc:
            self.sub_status.setText(f"Snapshot error: {exc}")

    def set_speed(self, rate: float):
        try:
            if self._player:
                self._player.set_rate(rate)
                self.speed_btn.setText(f"⚡ {rate:.2f}x".replace(".00x", ".0x"))
        except Exception:
            pass

    def set_aspect_ratio(self, ratio: str | None):
        try:
            if self._player:
                self._player.video_set_aspect_ratio(ratio.encode("utf-8") if ratio else None)
                label = ratio if ratio else "Fit"
                self.aspect_btn.setText(f"📐 {label}")
        except Exception:
            pass

    def adjust_audio_delay(self, delta_ms: int):
        try:
            if self._player:
                self._audio_delay_ms += delta_ms
                # VLC audio delay is in microseconds
                self._player.audio_set_delay(self._audio_delay_ms * 1000)
                self.sub_status.setText(f"Audio Delay: {self._audio_delay_ms} ms")
                QTimer.singleShot(3000, lambda: self.sub_status.setText(""))
        except Exception:
            pass

    def adjust_sub_delay(self, delta_ms: int):
        try:
            if self._player:
                self._sub_delay_ms += delta_ms
                # VLC subtitle delay is in microseconds
                self._player.video_set_spu_delay(self._sub_delay_ms * 1000)
                self.sub_status.setText(f"Subtitle Delay: {self._sub_delay_ms} ms")
                QTimer.singleShot(3000, lambda: self.sub_status.setText(""))
        except Exception:
            pass

    def _on_volume(self, val: int):
        try:
            if self._player:
                self._player.audio_set_volume(val)
                self.vol_lbl.setText(f"{val}%")
                if val == 0:
                    self.vol_btn.setText("🔇")
                elif val > 100:
                    self.vol_btn.setText("🔊+")
                else:
                    self.vol_btn.setText("🔊")
                self._is_muted = (val == 0)
        except Exception:
            pass

    def _on_slider_moved(self, val: int):
        try:
            if self._player:
                length = self._player.get_length()
                if length > 0:
                    self.cur_lbl.setText(_fmt(int((val / 1000.0) * length)))
        except Exception:
            pass

    def _on_slider_released(self):
        try:
            if self._player:
                length = self._player.get_length()
                if length > 0:
                    target = int((self.timeline.value() / 1000.0) * length)
                    self._player.set_time(target)
        except Exception:
            pass
        self._user_is_sliding = False

    def _on_poll(self):
        try:
            if not self._player:
                return
            length = self._player.get_length()
            cur = self._player.get_time()
            if length > 0:
                self.dur_lbl.setText(_fmt(length))
                if cur >= 0 and not self._user_is_sliding:
                    self.cur_lbl.setText(_fmt(cur))
                    frac = min(1.0, max(0.0, cur / float(length)))
                    self.timeline.setValue(int(frac * 1000))
                if int(cur / 1000) % 5 == 0:
                    self._save_pos()
        except Exception:
            pass

    def _save_pos(self):
        try:
            if self._player and self.movie_path:
                cur_ms = self._player.get_time()
                len_ms = self._player.get_length()
                if cur_ms > 0 and len_ms > 0:
                    save_playback_position(
                        self.movie_path, cur_ms / 1000.0, len_ms / 1000.0
                    )
        except Exception:
            pass

    # ── Context & Dropdown Menus ──────────────────────────────────────────────

    def _apply_menu_style(self, menu: QMenu):
        menu.setStyleSheet(
            "QMenu { background-color: #0E0C22; color: #E8F4FF; border: 1px solid rgba(0,240,255,50); "
            "  border-radius: 8px; padding: 6px; font-size: 12px; }"
            "QMenu::item { padding: 6px 20px; border-radius: 4px; }"
            "QMenu::item:selected { background-color: rgba(0,240,255,40); color: #00F0FF; }"
            "QMenu::separator { height: 1px; background: rgba(0,240,255,25); margin: 4px 0; }"
        )

    def _show_audio_tracks_menu(self):
        if not self._player:
            return
        menu = QMenu(self)
        self._apply_menu_style(menu)

        tracks = self._player.audio_get_track_description() or []
        curr_track = self._player.audio_get_track()

        if not tracks or len(tracks) == 0:
            act = menu.addAction("No Audio Tracks Available")
            act.setEnabled(False)
        else:
            for track_id, track_name in tracks:
                name_str = track_name.decode("utf-8") if isinstance(track_name, bytes) else str(track_name)
                act = menu.addAction(f"{'✔ ' if track_id == curr_track else '   '}{name_str}")
                act.triggered.connect(lambda _, tid=track_id: self._player.audio_set_track(tid))

        menu.addSeparator()
        delay_menu = menu.addMenu("🔊 Audio Sync / Delay")
        self._apply_menu_style(delay_menu)
        for label, d in [("-500 ms", -500), ("-100 ms", -100), ("Reset", 0), ("+100 ms", 100), ("+500 ms", 500)]:
            act = delay_menu.addAction(label)
            if d == 0:
                act.triggered.connect(lambda: setattr(self, "_audio_delay_ms", 0) or self._player.audio_set_delay(0))
            else:
                act.triggered.connect(lambda _, ms=d: self.adjust_audio_delay(ms))

        menu.exec(self.audio_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _show_subtitles_menu(self):
        if not self._player:
            return
        menu = QMenu(self)
        self._apply_menu_style(menu)

        tracks = self._player.video_get_spu_description() or []
        curr_spu = self._player.video_get_spu()

        for track_id, track_name in tracks:
            name_str = track_name.decode("utf-8") if isinstance(track_name, bytes) else str(track_name)
            act = menu.addAction(f"{'✔ ' if track_id == curr_spu else '   '}{name_str}")
            act.triggered.connect(lambda _, tid=track_id: self._player.video_set_spu(tid))

        menu.addSeparator()
        fetch_act = menu.addAction("🔍 Auto-Download Subtitles")
        fetch_act.triggered.connect(self.auto_fetch_subtitles)

        load_act = menu.addAction("📂 Load External Subtitle File (.srt/.ass)")
        load_act.triggered.connect(self.load_external_subtitle_dialog)

        menu.addSeparator()
        delay_menu = menu.addMenu("💬 Subtitle Sync / Delay")
        self._apply_menu_style(delay_menu)
        for label, d in [("-1 sec", -1000), ("-250 ms", -250), ("Reset", 0), ("+250 ms", 250), ("+1 sec", 1000)]:
            act = delay_menu.addAction(label)
            if d == 0:
                act.triggered.connect(lambda: setattr(self, "_sub_delay_ms", 0) or self._player.video_set_spu_delay(0))
            else:
                act.triggered.connect(lambda _, ms=d: self.adjust_sub_delay(ms))

        menu.exec(self.sub_menu_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _show_speed_menu(self):
        if not self._player:
            return
        menu = QMenu(self)
        self._apply_menu_style(menu)

        curr_rate = round(self._player.get_rate(), 2)
        speeds = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]

        for s in speeds:
            act = menu.addAction(f"{'✔ ' if abs(s - curr_rate) < 0.05 else '   '}{s}x Normal")
            act.triggered.connect(lambda _, r=s: self.set_speed(r))

        menu.exec(self.speed_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _show_aspect_menu(self):
        if not self._player:
            return
        menu = QMenu(self)
        self._apply_menu_style(menu)

        ratios = [("Original / Fit", None), ("16:9 Widescreen", "16:9"),
                  ("4:3 Standard", "4:3"), ("21:9 CinemaScope", "21:9"),
                  ("16:10", "16:10"), ("1:1 Square", "1:1")]

        for label, val in ratios:
            act = menu.addAction(label)
            act.triggered.connect(lambda _, r=val: self.set_aspect_ratio(r))

        menu.exec(self.aspect_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _show_context_menu(self, pos: QPoint):
        if not self._player:
            return
        menu = QMenu(self)
        self._apply_menu_style(menu)

        play_act = menu.addAction("▶ Pause" if self._player.is_playing() else "▶ Play")
        play_act.triggered.connect(self.toggle_play)

        fs_act = menu.addAction("⤢ Fullscreen (F)")
        fs_act.triggered.connect(self.toggle_fullscreen)

        snap_act = menu.addAction("📸 Take Snapshot (S)")
        snap_act.triggered.connect(self.take_snapshot)

        frame_act = menu.addAction("⏭ Next Frame (E)")
        frame_act.triggered.connect(self.next_frame)

        menu.addSeparator()

        # Submenus
        audio_sub = menu.addMenu("🎵 Audio Track")
        self._apply_menu_style(audio_sub)
        tracks = self._player.audio_get_track_description() or []
        curr_track = self._player.audio_get_track()
        for track_id, track_name in tracks:
            name_str = track_name.decode("utf-8") if isinstance(track_name, bytes) else str(track_name)
            act = audio_sub.addAction(f"{'✔ ' if track_id == curr_track else '   '}{name_str}")
            act.triggered.connect(lambda _, tid=track_id: self._player.audio_set_track(tid))

        sub_sub = menu.addMenu("💬 Subtitles")
        self._apply_menu_style(sub_sub)
        spus = self._player.video_get_spu_description() or []
        curr_spu = self._player.video_get_spu()
        for spu_id, spu_name in spus:
            name_str = spu_name.decode("utf-8") if isinstance(spu_name, bytes) else str(spu_name)
            act = sub_sub.addAction(f"{'✔ ' if spu_id == curr_spu else '   '}{name_str}")
            act.triggered.connect(lambda _, sid=spu_id: self._player.video_set_spu(sid))
        sub_sub.addSeparator()
        sub_sub.addAction("🔍 Auto-Download Subtitles").triggered.connect(self.auto_fetch_subtitles)
        sub_sub.addAction("📂 Load Subtitle File").triggered.connect(self.load_external_subtitle_dialog)

        speed_sub = menu.addMenu("⚡ Playback Speed")
        self._apply_menu_style(speed_sub)
        curr_rate = round(self._player.get_rate(), 2)
        for s in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            act = speed_sub.addAction(f"{'✔ ' if abs(s - curr_rate) < 0.05 else '   '}{s}x")
            act.triggered.connect(lambda _, r=s: self.set_speed(r))

        aspect_sub = menu.addMenu("📐 Aspect Ratio")
        self._apply_menu_style(aspect_sub)
        for label, val in [("Fit", None), ("16:9", "16:9"), ("4:3", "4:3"), ("21:9", "21:9")]:
            act = aspect_sub.addAction(label)
            act.triggered.connect(lambda _, r=val: self.set_aspect_ratio(r))

        menu.addSeparator()
        back_act = menu.addAction("⤺ Exit Player")
        back_act.triggered.connect(self.close_player)

        menu.exec(pos)

    # ── Keyboard Controls ─────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        mod = event.modifiers()

        if k in (Qt.Key_Space, Qt.Key_K):
            self.toggle_play()
        elif k == Qt.Key_Left:
            if mod & Qt.ControlModifier:
                self.seek_relative(-60000)
            elif mod & Qt.ShiftModifier:
                self.seek_relative(-5000)
            else:
                self.seek_relative(-10000)
        elif k == Qt.Key_Right:
            if mod & Qt.ControlModifier:
                self.seek_relative(60000)
            elif mod & Qt.ShiftModifier:
                self.seek_relative(5000)
            else:
                self.seek_relative(10000)
        elif k == Qt.Key_Up:
            self.vol_slider.setValue(min(200, self.vol_slider.value() + 5))
        elif k == Qt.Key_Down:
            self.vol_slider.setValue(max(0, self.vol_slider.value() - 5))
        elif k == Qt.Key_F:
            self.toggle_fullscreen()
        elif k == Qt.Key_M:
            self.toggle_mute()
        elif k == Qt.Key_S:
            self.take_snapshot()
        elif k == Qt.Key_E:
            self.next_frame()
        elif k == Qt.Key_A:
            self._cycle_audio_track()
        elif k == Qt.Key_V:
            self._cycle_sub_track()
        elif k == Qt.Key_Escape:
            self.close_player()
        else:
            super().keyPressEvent(event)

    def _cycle_audio_track(self):
        try:
            if not self._player:
                return
            tracks = self._player.audio_get_track_description() or []
            if len(tracks) <= 1:
                return
            curr = self._player.audio_get_track()
            ids = [t[0] for t in tracks]
            next_idx = (ids.index(curr) + 1) % len(ids) if curr in ids else 0
            self._player.audio_set_track(ids[next_idx])
            name = tracks[next_idx][1]
            name_str = name.decode("utf-8") if isinstance(name, bytes) else str(name)
            self.sub_status.setText(f"🎵 Audio: {name_str}")
            QTimer.singleShot(2500, lambda: self.sub_status.setText(""))
        except Exception:
            pass

    def _cycle_sub_track(self):
        try:
            if not self._player:
                return
            spus = self._player.video_get_spu_description() or []
            if len(spus) <= 1:
                return
            curr = self._player.video_get_spu()
            ids = [s[0] for s in spus]
            next_idx = (ids.index(curr) + 1) % len(ids) if curr in ids else 0
            self._player.video_set_spu(ids[next_idx])
            name = spus[next_idx][1]
            name_str = name.decode("utf-8") if isinstance(name, bytes) else str(name)
            self.sub_status.setText(f"💬 Subtitle: {name_str}")
            QTimer.singleShot(2500, lambda: self.sub_status.setText(""))
        except Exception:
            pass

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def close_player(self):
        self._save_pos()
        try:
            if self._player:
                self._player.stop()
        except Exception:
            pass
        try:
            if self._player:
                self._player.release()
        except Exception:
            pass
        try:
            if self._vlc_instance:
                self._vlc_instance.release()
        except Exception:
            pass

        self._player = None
        self._vlc_instance = None
        self._hwnd_bound = False
        self._init_vlc()

        self.movie_path = ""
        self.play_btn.setText("▶")
        self.timeline.setValue(0)
        self.cur_lbl.setText("00:00")
        self.dur_lbl.setText("00:00")
        self.closed.emit()

    def closeEvent(self, event):
        self.close_player()
        super().closeEvent(event)
