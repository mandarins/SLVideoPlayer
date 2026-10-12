# SLVideoPlayer.py - Main application file
import sys
import os
import locale
import string
import tempfile
import json
import math
from pathlib import Path

# Fix MPV DLL path for Windows
if sys.platform == 'win32':
    # Add current directory to PATH so libmpv-2.dll can be found
    os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ["PATH"]

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QSlider, QLabel,
                             QFileDialog, QToolBar, QStyle, QMessageBox,
                             QComboBox, QSpinBox, QInputDialog, QGraphicsOpacityEffect,
                             QStyleOptionSlider)
from PyQt6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QPoint, QRect, QRectF, QEvent
from PyQt6.QtGui import QAction, QKeySequence, QCursor, QFont, QPainter, QPen, QColor, QBrush
import mpv
from color_dialog import ColorCorrectionDialog
from recent_files_dialog import RecentFilesDialog
from settings import Settings
from settings_dialog import SettingsDialog

class BufferedSlider(QSlider):
    """Horizontal slider that draws a semi-transparent buffer-fill behind the handle."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._buffer_pct = 0

    def set_buffer(self, pct):
        pct = max(0, min(100, int(pct)))
        if self._buffer_pct != pct:
            self._buffer_pct = pct
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._buffer_pct <= 0:
            return
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt,
            QStyle.SubControl.SC_SliderGroove, self
        )
        if groove.width() > 0:
            buf_rect = groove.adjusted(0, 0, 0, 0)
            buf_rect.setWidth(int(groove.width() * self._buffer_pct / 100))
            painter = QPainter(self)
            painter.fillRect(buf_rect, QColor(80, 140, 255, 75))
            painter.end()


class ZoomOverlay(QWidget):
    """Captures Shift+drag over the video and zooms to the selected region.

    The selection box is drawn with mpv's OSD because mpv's native video window
    paints over any Qt widget stacked on top of it.
    """

    OSD_ID = 1
    BOX_STYLE = "{\\an7\\pos(0,0)\\bord2\\shad0\\1c&HD77800&\\1a&HC0&\\3c&HD77800&\\p1}"

    def __init__(self, parent, player_ref):
        super().__init__(parent)
        self.player_ref = player_ref  # reference to VideoPlayer instance
        self._origin = None
        self.hide()  # hidden until Shift is held

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._draw_box(self._selection(event.position()))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = self._selection(event.position())
        self.cancel()
        if rect.width() > 10:  # ignore accidental clicks
            self._zoom_to(rect)

    def cancel(self):
        self._origin = None
        self.player_ref.player.command('osd-overlay', self.OSD_ID, 'none', '')

    def _selection(self, pos):
        """Box from the drag origin toward pos, locked to the view's aspect ratio so it fills the view exactly."""
        aspect = self.width() / self.height()
        dx = pos.x() - self._origin.x()
        dy = pos.y() - self._origin.y()
        w = max(abs(dx), abs(dy) * aspect)
        h = w / aspect
        x = self._origin.x() - w if dx < 0 else self._origin.x()
        y = self._origin.y() - h if dy < 0 else self._origin.y()
        return QRectF(x, y, w, h)

    def _draw_box(self, r):
        path = (f"m {r.left():.0f} {r.top():.0f} l {r.right():.0f} {r.top():.0f} "
                f"{r.right():.0f} {r.bottom():.0f} {r.left():.0f} {r.bottom():.0f}")
        self.player_ref.player.command('osd-overlay', self.OSD_ID, 'ass-events',
                                       self.BOX_STYLE + path, self.width(), self.height())

    def _zoom_to(self, rect):
        vp = self.player_ref
        osd = vp.player.osd_dimensions
        # osd-dimensions are in physical pixels and include letterboxing plus any current zoom/pan
        scale = osd['w'] / self.width()
        video_w = osd['w'] - osd['ml'] - osd['mr']
        video_h = osd['h'] - osd['mt'] - osd['mb']
        fx = (rect.center().x() * scale - osd['ml']) / video_w
        fy = (rect.center().y() * scale - osd['mt']) / video_h
        current_zoom = 2 ** (vp.player.video_zoom or 0)
        vp.zoom_spinbox.setValue(round(current_zoom * self.width() / rect.width() * 100))
        # Pan is in fractions of the scaled video, so this centres the selection at any zoom
        vp.player.video_pan_x = 0.5 - fx
        vp.player.video_pan_y = 0.5 - fy


class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.bookmarks = []
        self.screenshot_counter = 1  # Sequential counter for screenshots
        self.recent_files = []  # List to store recent files
        self.max_recent_files = 50  # Maximum number of recent files to keep
        self.recent_files_path = "recent_files.json"  # File to save recent files
        self.settings = Settings()  # Initialize settings
        self._drag_last = None  # last mouse position while drag-panning
        
        # Frame stepping mode variables
        self.frame_step_mode = False
        
        self.load_recent_files()  # Load recent files from disk
        self.init_ui()
        self.init_player()
        QApplication.instance().installEventFilter(self)
        
    def init_ui(self):
        self.setWindowTitle("Advanced Video Player")
        self.setGeometry(100, 100, 1280, 720)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create toolbar
        self.create_toolbar()
        
        # Video container
        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.setMinimumSize(640, 480)
        main_layout.addWidget(self.video_widget, stretch=1)

        # Transparent overlay for Shift+drag region zoom
        self.zoom_overlay = ZoomOverlay(self.video_widget, self)
        self.zoom_overlay.setGeometry(self.video_widget.rect())
        
        # Controls layout
        controls_layout = QVBoxLayout()
        
        # Progress bar
        progress_layout = QHBoxLayout()
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.progress_slider = BufferedSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.sliderMoved.connect(self.seek_video)
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress_slider)
        controls_layout.addLayout(progress_layout)
        
        # Playback controls
        playback_layout = QHBoxLayout()
        
        # Play/Pause button
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play_pause)
        playback_layout.addWidget(self.play_button)
        
        # Stop button
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self.stop_video)
        playback_layout.addWidget(stop_button)
        
        # Frame Step Mode Toggle
        self.frame_step_button = QPushButton("Frame Step Mode: OFF")
        self.frame_step_button.setCheckable(True)
        self.frame_step_button.clicked.connect(self.toggle_frame_step_mode)
        self.frame_step_button.setToolTip("Enable frame-by-frame navigation with mouse wheel")
        playback_layout.addWidget(self.frame_step_button)
        
        # Speed control
        playback_layout.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x", "3.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self.change_speed)
        playback_layout.addWidget(self.speed_combo)
        
        # Zoom control
        playback_layout.addWidget(QLabel("Zoom:"))
        self.zoom_spinbox = QSpinBox()
        self.zoom_spinbox.setRange(50, 1000)
        self.zoom_spinbox.setValue(100)
        self.zoom_spinbox.setSuffix("%")
        self.zoom_spinbox.valueChanged.connect(self.apply_zoom)
        playback_layout.addWidget(self.zoom_spinbox)
        
        # Aspect ratio
        playback_layout.addWidget(QLabel("Aspect:"))
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["Default", "16:9", "4:3", "21:9", "1:1", "Stretch"])
        self.aspect_combo.currentTextChanged.connect(self.change_aspect_ratio)
        playback_layout.addWidget(self.aspect_combo)
        
        playback_layout.addStretch()
        
        # Volume control
        playback_layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        playback_layout.addWidget(self.volume_slider)
        
        controls_layout.addLayout(playback_layout)
        
        # Bookmark controls
        bookmark_layout = QHBoxLayout()
        self.mark_in_button = QPushButton("Mark In [I]")
        self.mark_in_button.clicked.connect(self.mark_in)
        bookmark_layout.addWidget(self.mark_in_button)
        
        self.mark_out_button = QPushButton("Mark Out [O]")
        self.mark_out_button.clicked.connect(self.mark_out)
        bookmark_layout.addWidget(self.mark_out_button)
        
        self.replay_section_button = QPushButton("Replay Section [R]")
        self.replay_section_button.clicked.connect(self.replay_section)
        bookmark_layout.addWidget(self.replay_section_button)
        
        self.export_section_button = QPushButton("Export Section")
        self.export_section_button.clicked.connect(self.export_section)
        bookmark_layout.addWidget(self.export_section_button)
        
        bookmark_layout.addStretch()
        controls_layout.addLayout(bookmark_layout)
        
        main_layout.addLayout(controls_layout)
        
        # Timer for updating progress
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(100)
        
        # Initialize bookmark positions
        self.mark_in_pos = None
        self.mark_out_pos = None

        self.setAcceptDrops(True)

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Open file
        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)
        
        # Direct path entry
        path_action = QAction("Open Path", self)
        path_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        path_action.triggered.connect(self.open_path_directly)
        toolbar.addAction(path_action)
        
        # Native Network Browser
        network_action = QAction("Network", self)
        network_action.setShortcut(QKeySequence("Ctrl+N"))
        network_action.triggered.connect(self.open_file_native_network)
        toolbar.addAction(network_action)

        # Stream URL
        stream_action = QAction("Stream URL", self)
        stream_action.setShortcut(QKeySequence("Ctrl+U"))
        stream_action.triggered.connect(self.open_url)
        toolbar.addAction(stream_action)

        toolbar.addSeparator()
        
        # Screenshot
        screenshot_action = QAction("Screenshot", self)
        screenshot_action.setShortcut(QKeySequence("Ctrl+S"))
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)
        
        toolbar.addSeparator()
        
        # Delete video file
        delete_action = QAction("Delete Video", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self.delete_video_file)
        toolbar.addAction(delete_action)
        
        toolbar.addSeparator()
        
        # Rotate
        rotate_left_action = QAction("Rotate Left", self)
        rotate_left_action.triggered.connect(lambda: self.rotate_video(-90))
        toolbar.addAction(rotate_left_action)
        
        rotate_right_action = QAction("Rotate Right", self)
        rotate_right_action.triggered.connect(lambda: self.rotate_video(90))
        toolbar.addAction(rotate_right_action)
        
        toolbar.addSeparator()
        
        # Reset view
        reset_action = QAction("Reset View", self)
        reset_action.setShortcut(QKeySequence("Ctrl+R"))
        reset_action.triggered.connect(self.reset_view)
        toolbar.addAction(reset_action)
        
        toolbar.addSeparator()
        
        # Color Correction
        color_action = QAction("Color", self)
        color_action.setShortcut(QKeySequence("Ctrl+L"))
        color_action.triggered.connect(self.open_color_correction)
        toolbar.addAction(color_action)
        
        toolbar.addSeparator()
        
        # Recent Files
        recent_action = QAction("Recent", self)
        recent_action.setShortcut(QKeySequence("Ctrl+H"))
        recent_action.triggered.connect(self.show_recent_files)
        toolbar.addAction(recent_action)

        # Settings
        settings_action = QAction("Settings", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)
        
        toolbar.addSeparator()

    def init_player(self):
        # mpv auto-picks Wayland when WAYLAND_DISPLAY is set, opening its own surface instead of embedding.
        # Its X11 window also swallows mouse and key events, so leave input to Qt (Shift+drag zoom, wheel stepping).
        linux_opts = ({'gpu_context': 'x11egl', 'input_cursor': False, 'input_vo_keyboard': False}
                      if sys.platform.startswith('linux') else {'input_vo_keyboard': True})
        try:
            self.player = mpv.MPV(
                **linux_opts,
                wid=str(int(self.video_widget.winId())),
                input_default_bindings=True,
                hwdec='no',
                vo='gpu',
                keep_open='yes',
                loop='no',
                deinterlace=True,
                cache='yes',
                demuxer_max_bytes=67108864,   # 64 MB forward buffer
                demuxer_readahead_secs=30,    # buffer up to 30 s ahead
            )
            self.player.volume = 50
            self.current_rotation = 0
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to initialize player: {str(e)}\n\nMake sure libmpv-2.dll is in the same folder as this script.")
            sys.exit(1)
    
    def toggle_frame_step_mode(self):
        """Toggle frame stepping mode on/off"""
        self.frame_step_mode = self.frame_step_button.isChecked()
        
        if self.frame_step_mode:
            self.frame_step_button.setText("Frame Step Mode: ON")
            self.frame_step_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            
            # Pause video when entering frame step mode
            if not self.player.pause:
                self.player.pause = True
                self.play_button.setText("Play")
            
            QMessageBox.information(self, "Frame Step Mode", 
                "Frame Step Mode enabled!\n\n"
                "Scroll mouse wheel FORWARD to step forward frame by frame.\n"
                "Scroll mouse wheel BACKWARD to step backward frame by frame.\n\n"
                "Click the button again to exit this mode.")
        else:
            self.frame_step_button.setText("Frame Step Mode: OFF")
            self.frame_step_button.setStyleSheet("")
    
    def wheelEvent(self, event):
        """Handle mouse wheel for frame stepping"""
        # Only process wheel events in frame step mode
        if not self.frame_step_mode:
            super().wheelEvent(event)
            return
        
        # Get wheel delta (positive = scroll up/forward, negative = scroll down/backward)
        delta = event.angleDelta().y()
        
        if delta > 0:
            # Scroll forward - step forward one frame
            try:
                self.player.command('frame-step')
            except Exception as e:
                print(f"Error stepping frame forward: {e}")
        elif delta < 0:
            # Scroll backward - step backward one frame
            try:
                self.player.command('frame-back-step')
            except Exception as e:
                print(f"Error stepping frame backward: {e}")
        
        # Accept the event to prevent it from propagating
        event.accept()
    
    def get_all_drives(self):
        """Get all available drives including mapped network drives using multiple detection methods"""
        import subprocess
        
        drives = []
        
        # Method 1: Check each letter with os.path.exists
        print("\n=== Method 1: Checking A-Z with os.path.exists ===")
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(drive_path)
                print(f"Found: {drive_path}")
        
        # Method 2: Use wmic (Windows Management Instrumentation Command-line)
        print("\n=== Method 2: Using WMIC ===")
        try:
            result = subprocess.run(
                ['wmic', 'logicaldisk', 'get', 'name'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and ':' in line and len(line) <= 3:
                    drive_path = line if line.endswith('\\') else line + '\\'
                    if drive_path not in drives:
                        drives.append(drive_path)
                        print(f"Found via WMIC: {drive_path}")
        except Exception as e:
            print(f"WMIC failed: {e}")
        
        # Method 3: Parse 'net use' output
        print("\n=== Method 3: Using 'net use' ===")
        try:
            result = subprocess.run(
                ['net', 'use'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print(result.stdout)
            for line in result.stdout.splitlines():
                if ':' in line and 'OK' in line:
                    parts = line.split()
                    for part in parts:
                        if len(part) == 2 and part[1] == ':':
                            drive_path = part + '\\'
                            if drive_path not in drives:
                                drives.append(drive_path)
                                print(f"Found via net use: {drive_path}")
        except Exception as e:
            print(f"net use failed: {e}")
        
        # Sort drives alphabetically
        drives = sorted(set(drives))
        
        print(f"\n=== Final detected drives: {drives} ===\n")
        return drives
    
    def open_file(self):
        """Open file dialog with support for all drives including mapped ones"""
        # Get all available drives
        available_drives = self.get_all_drives()
        
        # Print drives to console for debugging
        print(f"Available drives detected: {', '.join(available_drives)}")
        
        # Remember last folder used
        if hasattr(self, 'last_folder') and os.path.exists(self.last_folder):
            start_path = self.last_folder
        else:
            # Default to C:\ or first available drive
            start_path = "C:\\" if "C:\\" in available_drives else (available_drives[0] if available_drives else "")
        
        # Create file dialog
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Open Video File")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("Video Files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v *.mpg *.mpeg);;All Files (*.*)")
        
        # CRITICAL: Use non-native dialog
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setOption(QFileDialog.Option.DontResolveSymlinks, False)
        
        # Set starting directory
        if start_path:
            dialog.setDirectory(start_path)
        
        # Build sidebar with all drives
        sidebar_urls = []
        
        # Add common Windows locations
        sidebar_urls.append(QUrl.fromLocalFile(os.path.expanduser("~")))  # User home
        sidebar_urls.append(QUrl.fromLocalFile(os.path.expanduser("~/Desktop")))
        sidebar_urls.append(QUrl.fromLocalFile(os.path.expanduser("~/Documents")))
        sidebar_urls.append(QUrl.fromLocalFile(os.path.expanduser("~/Videos")))
        
        # Add all detected drives
        for drive in available_drives:
            sidebar_urls.append(QUrl.fromLocalFile(drive))
        
        # Set the sidebar URLs
        dialog.setSidebarUrls(sidebar_urls)
        
        # Execute dialog
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                file_path = files[0]
                
                # Remember the folder for next time
                self.last_folder = os.path.dirname(file_path)
                
                self.load_video(file_path)
    
    def open_file_native_network(self):
        """Open file using Windows native dialog - best for network browsing"""
        # Remember last folder
        if hasattr(self, 'last_folder') and os.path.exists(self.last_folder):
            start_path = self.last_folder
        else:
            start_path = ""
        
        # Use NATIVE Windows dialog - this one shows Network properly!
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video File (Network Browser)",
            start_path,
            "Video Files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v *.mpg *.mpeg);;All Files (*.*)"
            # NOTE: No DontUseNativeDialog option - this uses Windows native dialog
        )
        
        if file_path:
            self.last_folder = os.path.dirname(file_path)
            self.load_video(file_path)
    
    def open_url(self):
        """Open a streaming URL (HTTP, HTTPS, RTSP, RTMP, HLS, etc.)"""
        url, ok = QInputDialog.getText(
            self,
            "Open Stream URL",
            "Enter stream URL (http://, https://, rtsp://, rtmp://, hls://):",
            text="https://"
        )
        if ok and url.strip():
            self.load_video(url.strip())

    def open_path_directly(self):
        """Open a file by typing/pasting the full path - works with UNC paths and mapped drives"""
        # Get all available drives
        available_drives = self.get_all_drives()
        drives_list = [d[:-1] for d in available_drives]  # Remove trailing backslash
        
        # Build info text with network paths
        info_text = "Available drives: " + ", ".join(drives_list) if drives_list else "Only C:\\ detected"
        info_text += "\n\nYour network shares:\n"
        info_text += "  \\\\192.168.50.79\\slentini\n"
        info_text += "  \\\\192.168.50.154\\sharedfolder\n"
        info_text += "\nEnter full path (drive letter or UNC path):"
        
        # Get default text - try last folder or suggest network path
        if hasattr(self, 'last_folder') and self.last_folder:
            default_text = self.last_folder
        else:
            # Suggest the network path
            default_text = "\\\\192.168.50.79\\slentini\\"
        
        file_path, ok = QInputDialog.getText(
            self,
            "Open File by Path",
            info_text,
            text=default_text
        )
        
        if ok and file_path:
            file_path = file_path.strip().strip('"')  # Remove quotes if pasted
            
            # Handle drive letter (e.g., "C:" or "X:")
            if len(file_path) <= 3 and ':' in file_path:
                if not file_path.endswith('\\'):
                    file_path += '\\'
                
                # Try to open file dialog at this location
                if os.path.exists(file_path):
                    dialog = QFileDialog(self)
                    dialog.setWindowTitle(f"Browse {file_path}")
                    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
                    dialog.setNameFilter("Video Files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v *.mpg *.mpeg);;All Files (*.*)")
                    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
                    dialog.setDirectory(file_path)
                    
                    if dialog.exec() == QFileDialog.DialogCode.Accepted:
                        files = dialog.selectedFiles()
                        if files:
                            self.last_folder = os.path.dirname(files[0])
                            self.load_video(files[0])
                else:
                    QMessageBox.warning(self, "Drive Not Found", 
                        f"Cannot access: {file_path}\n\n"
                        f"The drive may not be mapped in this context.\n"
                        f"Try using the UNC path instead:\n"
                        f"\\\\192.168.50.79\\slentini\\")
                return
            
            # Handle UNC path or folder path
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    self.last_folder = os.path.dirname(file_path)
                    self.load_video(file_path)
                elif os.path.isdir(file_path):
                    # Open file dialog at this location
                    dialog = QFileDialog(self)
                    dialog.setWindowTitle(f"Browse {file_path}")
                    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
                    dialog.setNameFilter("Video Files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v *.mpg *.mpeg);;All Files (*.*)")
                    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
                    dialog.setDirectory(file_path)
                    
                    if dialog.exec() == QFileDialog.DialogCode.Accepted:
                        files = dialog.selectedFiles()
                        if files:
                            self.last_folder = os.path.dirname(files[0])
                            self.load_video(files[0])
                else:
                    QMessageBox.warning(self, "Not a File", f"Exists but is not a file:\n{file_path}")
            else:
                QMessageBox.warning(self, "Path Not Found", 
                    f"Could not find:\n{file_path}\n\n"
                    f"Tips:\n"
                    f"- For X: drive, try: \\\\192.168.50.79\\slentini\\\n"
                    f"- For L: drive, try: \\\\192.168.50.154\\sharedfolder\\\n"
                    f"- Check the path spelling\n"
                    f"- Make sure you have network access")
    
    def load_video(self, file_path):
        """Load and play a video file or stream URL"""
        try:
            self.current_file = file_path
            self.player.play(file_path)
            self.play_button.setText("Pause")
            if '://' in file_path:
                from urllib.parse import urlparse
                parsed = urlparse(file_path)
                display_name = parsed.path.rstrip('/').split('/')[-1] or parsed.netloc or file_path
            else:
                display_name = Path(file_path).name
            self.setWindowTitle(f"Video Player - {display_name}")
            self.mark_in_pos = None
            self.mark_out_pos = None
            # Reset screenshot counter for new video
            self.screenshot_counter = 1
            
            # Add to recent files
            self.add_to_recent_files(file_path)
            
            print(f"Successfully loaded: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Video", 
                f"Failed to load video:\n{file_path}\n\nError: {str(e)}")
    
    def load_recent_files(self):
        """Load recent files from JSON file"""
        try:
            if os.path.exists(self.recent_files_path):
                with open(self.recent_files_path, 'r') as f:
                    self.recent_files = json.load(f)
                    # Keep only the last 50
                    self.recent_files = self.recent_files[-self.max_recent_files:]
        except Exception as e:
            print(f"Error loading recent files: {e}")
            self.recent_files = []

    def save_recent_files(self):
        """Save recent files to JSON file"""
        try:
            with open(self.recent_files_path, 'w') as f:
                json.dump(self.recent_files, f, indent=2)
        except Exception as e:
            print(f"Error saving recent files: {e}")

    def add_to_recent_files(self, file_path):
        """Add a file to recent files list"""
        # Remove if already exists (to move it to the end)
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        
        # Add to end of list
        self.recent_files.append(file_path)
        
        # Keep only last 50
        if len(self.recent_files) > self.max_recent_files:
            self.recent_files = self.recent_files[-self.max_recent_files:]
        
        # Save to disk
        self.save_recent_files()

    def show_recent_files(self):
        """Show the recent files dialog"""
        if not self.recent_files:
            QMessageBox.information(self, "No Recent Files", "No recent files to show.")
            return
        
        # Create and show dialog (reversed so newest is at top)
        dialog = RecentFilesDialog(list(reversed(self.recent_files)), self)
        dialog.file_selected.connect(self.load_video)
        dialog.exec()
        
        # Update recent files list in case user cleared it
        self.recent_files = list(reversed(dialog.recent_files))
        self.save_recent_files()

    def open_settings(self):
        """Open the settings dialog"""
        dialog = SettingsDialog(self.settings, self)
        dialog.exec()

    def toggle_play_pause(self):
        if self.player.pause:
            self.player.pause = False
            self.play_button.setText("Pause")
        else:
            self.player.pause = True
            self.play_button.setText("Play")
    
    def stop_video(self):
        self.player.stop()
        self.play_button.setText("Play")
    
    def seek_video(self, position):
        if self.player.duration:
            seek_time = (position / 100) * self.player.duration
            self.player.seek(seek_time, reference='absolute')
    
    def change_speed(self, speed_text):
        speed = float(speed_text.replace('x', ''))
        self.player.speed = speed
    
    def change_volume(self, value):
        self.player.volume = value
    
    def apply_zoom(self, value):
        zoom_factor = value / 100.0
        self.player.video_zoom = math.log2(zoom_factor)  # mpv zoom is a log2 scale
    
    def change_aspect_ratio(self, aspect):
        if aspect == "Default":
            self.player.video_aspect_override = "-1"
        elif aspect == "Stretch":
            self.player.video_aspect_override = "0"
            self.player.video_unscaled = "no"
        elif aspect == "16:9":
            self.player.video_aspect_override = "16:9"
        elif aspect == "4:3":
            self.player.video_aspect_override = "4:3"
        elif aspect == "21:9":
            self.player.video_aspect_override = "21:9"
        elif aspect == "1:1":
            self.player.video_aspect_override = "1:1"
    
    def rotate_video(self, degrees):
        self.current_rotation = (self.current_rotation + degrees) % 360
        self.player.video_rotate = self.current_rotation
    
    def reset_view(self):
        self.zoom_spinbox.setValue(100)
        self.aspect_combo.setCurrentText("Default")
        self.current_rotation = 0
        self.player.video_rotate = 0
        self.player.video_zoom = 0
        self.player.video_aspect_override = "-1"
        
        # Reset pan position
        try:
            self.player.video_pan_x = 0
            self.player.video_pan_y = 0
        except:
            pass
        
        # Reset color correction
        self.reset_color_correction()
        if hasattr(self, 'color_dialog'):
            self.color_dialog.set_values(0, 0, 0, 0, 0)
    
    def open_color_correction(self):
        """Open the color correction dialog"""
        if not hasattr(self, 'color_dialog'):
            # Create dialog if it doesn't exist
            self.color_dialog = ColorCorrectionDialog(self)
            
            # Connect signals to handler methods
            self.color_dialog.brightness_changed.connect(self.apply_brightness)
            self.color_dialog.contrast_changed.connect(self.apply_contrast)
            self.color_dialog.saturation_changed.connect(self.apply_saturation)
            self.color_dialog.gamma_changed.connect(self.apply_gamma)
            self.color_dialog.sharpness_changed.connect(self.apply_sharpness)
            self.color_dialog.reset_all.connect(self.reset_color_correction)
        
        # Show the dialog
        self.color_dialog.show()
        self.color_dialog.raise_()
        self.color_dialog.activateWindow()

    def apply_brightness(self, value):
        """Apply brightness adjustment to video"""
        try:
            self.player.brightness = value
        except Exception as e:
            print(f"Error setting brightness: {e}")

    def apply_contrast(self, value):
        """Apply contrast adjustment to video"""
        try:
            self.player.contrast = value
        except Exception as e:
            print(f"Error setting contrast: {e}")

    def apply_saturation(self, value):
        """Apply saturation adjustment to video"""
        try:
            self.player.saturation = value
        except Exception as e:
            print(f"Error setting saturation: {e}")

    def apply_gamma(self, value):
        """Apply gamma adjustment to video"""
        try:
            self.player.gamma = value
        except Exception as e:
            print(f"Error setting gamma: {e}")

    def apply_sharpness(self, value):
        """Apply sharpness adjustment to video via unsharp mask filter"""
        try:
            self.sharpness_value = value
            if value == 0:
                # Remove the unsharp filter
                self.player.vf = ""
            else:
                # Map slider 0-100 to unsharp amount 0.0-3.0
                amount = value / 100.0 * 3.0
                self.player.vf = f"lavfi=[unsharp=5:5:{amount:.2f}:5:5:{amount:.2f}]"
        except Exception as e:
            print(f"Error setting sharpness: {e}")

    def reset_color_correction(self):
        """Reset all color correction values"""
        try:
            self.player.brightness = 0
            self.player.contrast = 0
            self.player.saturation = 0
            self.player.gamma = 0
            self.sharpness_value = 0
            self.player.vf = ""
        except Exception as e:
            print(f"Error resetting color correction: {e}")
    
    def update_progress(self):
        """Update the progress bar, buffer indicator, and time display"""
        try:
            if not hasattr(self, 'player'):
                return

            if self.player.duration:
                current_time = self.player.time_pos or 0
                duration = self.player.duration

                progress = int((current_time / duration) * 100)
                self.progress_slider.blockSignals(True)
                self.progress_slider.setValue(progress)
                self.progress_slider.blockSignals(False)

                current_str = self.format_time(current_time)
                duration_str = self.format_time(duration)
                self.time_label.setText(f"{current_str} / {duration_str}")

                # Buffer indicator: use demuxer cache state to find cache end PTS
                try:
                    cache_state = self.player.demuxer_cache_state
                    if cache_state and 'cache-end' in cache_state:
                        buf_pct = int(min(100, cache_state['cache-end'] / duration * 100))
                    else:
                        buf_pct = 0
                except Exception:
                    buf_pct = 0
                self.progress_slider.set_buffer(buf_pct)
            else:
                self.progress_slider.set_buffer(0)
        except Exception:
            pass
    
    def format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def mark_in(self):
        if self.player.time_pos is not None:
            self.mark_in_pos = self.player.time_pos
            QMessageBox.information(self, "Mark In", f"Mark In set at {self.format_time(self.mark_in_pos)}")
    
    def mark_out(self):
        if self.player.time_pos is not None:
            self.mark_out_pos = self.player.time_pos
            QMessageBox.information(self, "Mark Out", f"Mark Out set at {self.format_time(self.mark_out_pos)}")
    
    def replay_section(self):
        if self.mark_in_pos is not None and self.mark_out_pos is not None:
            self.player.seek(self.mark_in_pos, reference='absolute')
            self.player.pause = False
            self.play_button.setText("Pause")
            QTimer.singleShot(100, self.check_section_end)
        else:
            QMessageBox.warning(self, "Warning", "Please set both Mark In and Mark Out points first")
    
    def check_section_end(self):
        if self.player.time_pos and self.player.time_pos >= self.mark_out_pos:
            self.player.seek(self.mark_in_pos, reference='absolute')
        if not self.player.pause:
            QTimer.singleShot(100, self.check_section_end)
    
    def export_section(self):
        if self.mark_in_pos is None or self.mark_out_pos is None:
            QMessageBox.warning(self, "Warning", "Please set both Mark In and Mark Out points first")
            return
        
        if not self.current_file:
            return
        
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Section",
            f"{Path(self.current_file).stem}_section.mp4",
            "Video Files (*.mp4)"
        )
        
        if save_path:
            try:
                import subprocess
                duration = self.mark_out_pos - self.mark_in_pos
                
                cmd = [
                    'ffmpeg',
                    '-i', self.current_file,
                    '-ss', str(self.mark_in_pos),
                    '-t', str(duration),
                    '-c', 'copy',
                    save_path
                ]
                
                subprocess.run(cmd, check=True)
                QMessageBox.information(self, "Success", f"Section exported to:\n{save_path}")
            except FileNotFoundError:
                QMessageBox.warning(self, "FFmpeg Not Found", 
                    "FFmpeg is required for exporting sections.\n"
                    "Download from: https://ffmpeg.org/download.html")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export section: {str(e)}")
    
    def get_next_screenshot_path(self, base_name, extension=".png"):
        """Generate the next available screenshot filename with sequential numbering"""
        if not self.current_file:
            return None
        
        # Get the download folder from settings
        download_folder = self.settings.get_download_folder()
        
        # Generate filename with sequential number
        while True:
            filename = f"{base_name}_{self.screenshot_counter:04d}{extension}"
            full_path = os.path.join(download_folder, filename)
            
            # Check if file exists
            if not os.path.exists(full_path):
                return full_path
            
            # If file exists, increment counter and try again
            self.screenshot_counter += 1
    
    def flash_text(self, message, duration=1500):
        """Show a temporary text overlay on the video widget that fades out"""
        label = QLabel(message, self.video_widget)
        label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 160); "
            "padding: 8px 16px; border-radius: 6px;"
        )
        label.adjustSize()
        # Center horizontally, position near bottom
        x = (self.video_widget.width() - label.width()) // 2
        y = self.video_widget.height() - label.height() - 40
        label.move(x, y)
        label.show()

        # Fade out animation
        opacity_effect = QGraphicsOpacityEffect(label)
        label.setGraphicsEffect(opacity_effect)
        fade = QPropertyAnimation(opacity_effect, b"opacity")
        fade.setDuration(duration)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InQuad)
        fade.finished.connect(label.deleteLater)
        fade.start()
        # Keep reference so animation isn't garbage collected
        label._fade_anim = fade

    def take_screenshot(self):
        """Take a screenshot of the current frame, respecting zoom"""
        if not self.current_file:
            return
        
        try:
            # Get base name from video file
            base_name = Path(self.current_file).stem
            
            # Get the next available screenshot path
            save_path = self.get_next_screenshot_path(base_name, ".png")
            
            if not save_path:
                self.flash_text("Could not determine save path")
                return
            
            # Check if we're zoomed
            current_zoom = self.zoom_spinbox.value()
            
            if current_zoom == 100:
                # No zoom, simple screenshot
                self.player.screenshot_to_file(save_path)
                self.screenshot_counter += 1
                self.flash_text(f"Screenshot saved: {Path(save_path).name}")
            else:
                # Zoomed - need to capture the zoomed area
                self.take_zoomed_screenshot(save_path)
                self.screenshot_counter += 1

        except Exception as e:
            self.flash_text(f"Screenshot failed: {str(e)}")

    def take_zoomed_screenshot(self, save_path):
        """Save the part of the frame currently visible in the window"""
        try:
            from PIL import Image
            
            # Take a full frame screenshot to temp file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                temp_path = tmp.name
            
            self.player.screenshot_to_file(temp_path)
            
            # Open the full frame
            img = Image.open(temp_path)
            width, height = img.size
            
            # Map the window onto the frame: osd-dimensions give where mpv draws the video,
            # already including zoom, pan and letterboxing
            osd = self.player.osd_dimensions
            scale = (osd['w'] - osd['ml'] - osd['mr']) / width
            left = max(0, int(-osd['ml'] / scale))
            top = max(0, int(-osd['mt'] / scale))
            right = min(width, int((osd['w'] - osd['ml']) / scale))
            bottom = min(height, int((osd['h'] - osd['mt']) / scale))
            
            # Crop the image
            cropped = img.crop((left, top, right, bottom))
            
            # Save the cropped image
            cropped.save(save_path)
            
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            
            self.flash_text(f"Screenshot saved: {Path(save_path).name} ({right-left}x{bottom-top})")

        except ImportError:
            self.player.screenshot_to_file(save_path)
            self.flash_text(f"Screenshot saved: {Path(save_path).name} (full frame, install Pillow for zoom crop)")

        except Exception as e:
            self.flash_text(f"Zoomed screenshot failed: {str(e)}")
    
    def delete_video_file(self):
        if not self.current_file:
            QMessageBox.warning(self, "No File", "No video file is currently loaded")
            return
        
        reply = QMessageBox.question(
            self,
            "Delete Video",
            f"Are you sure you want to permanently delete:\n{Path(self.current_file).name}\n\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                file_to_delete = self.current_file
                self.player.stop()
                self.current_file = None
                self.setWindowTitle("Advanced Video Player")
                
                os.remove(file_to_delete)
                QMessageBox.information(self, "Deleted", f"Video file deleted:\n{Path(file_to_delete).name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete file: {str(e)}")
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self.isActiveWindow():
            mods = event.modifiers()
            key = event.key()
            if (mods & Qt.KeyboardModifier.AltModifier) and key in (
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right
            ):
                self._apply_pan(key)
                return True  # consume — no widget zooms or scrolls
        if obj is self.video_widget and self.zoom_spinbox.value() > 100 and self._drag_pan(event):
            return True
        return super().eventFilter(obj, event)

    def _drag_pan(self, event):
        """Move the zoomed video with a left-button drag; returns True if the event was used."""
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_last = event.position()
            self.video_widget.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event_type == QEvent.Type.MouseMove and self._drag_last is not None:
            delta = event.position() - self._drag_last
            self._drag_last = event.position()
            # Pan is in fractions of the displayed video; osd-dimensions are physical pixels
            osd = self.player.osd_dimensions
            scale = osd['w'] / self.video_widget.width()
            self.player.video_pan_x = (self.player.video_pan_x or 0.0) + delta.x() * scale / (osd['w'] - osd['ml'] - osd['mr'])
            self.player.video_pan_y = (self.player.video_pan_y or 0.0) + delta.y() * scale / (osd['h'] - osd['mt'] - osd['mb'])
        elif event_type == QEvent.Type.MouseButtonRelease and self._drag_last is not None:
            self._drag_last = None
            self.video_widget.unsetCursor()
        else:
            return False
        return True

    def _apply_pan(self, key):
        if self.zoom_spinbox.value() <= 100:
            return
        pan_speed = 0.05
        try:
            if key == Qt.Key.Key_Left:
                self.player.video_pan_x = min(1.0, (self.player.video_pan_x or 0.0) + pan_speed)
            elif key == Qt.Key.Key_Right:
                self.player.video_pan_x = max(-1.0, (self.player.video_pan_x or 0.0) - pan_speed)
            elif key == Qt.Key.Key_Up:
                self.player.video_pan_y = min(1.0, (self.player.video_pan_y or 0.0) + pan_speed)
            elif key == Qt.Key.Key_Down:
                self.player.video_pan_y = max(-1.0, (self.player.video_pan_y or 0.0) - pan_speed)
        except Exception as e:
            print(f"Pan error: {e}")

    _VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v', '.mpg', '.mpeg'}

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in self._VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in self._VIDEO_EXTENSIONS:
                    self.load_video(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def keyPressEvent(self, event):
        # Get modifier keys
        modifiers = event.modifiers()
        key = event.key()

        # Shift held = show zoom-selection overlay
        if key == Qt.Key.Key_Shift:
            self.zoom_overlay.setGeometry(self.video_widget.rect())
            self.zoom_overlay.show()
            self.zoom_overlay.raise_()
            event.accept()
            return

        # Alt + Arrow keys = Pan (when zoomed)
        # MUST be checked FIRST before any other key handling
        if modifiers & Qt.KeyboardModifier.AltModifier:
            current_zoom = self.zoom_spinbox.value()
            pan_speed = 0.05  # Adjust for faster/slower panning
        
            if current_zoom > 100:  # Only pan when zoomed in
            
                if key == Qt.Key.Key_Left:
                    try:
                        current_pan_x = self.player.video_pan_x or 0.0
                        self.player.video_pan_x = min(1.0, current_pan_x + pan_speed)
                    except Exception as e:
                        print(f"Pan left error: {e}")

                elif key == Qt.Key.Key_Right:
                    try:
                        current_pan_x = self.player.video_pan_x or 0.0
                        self.player.video_pan_x = max(-1.0, current_pan_x - pan_speed)
                    except Exception as e:
                        print(f"Pan right error: {e}")

                elif key == Qt.Key.Key_Up:
                    try:
                        current_pan_y = self.player.video_pan_y or 0.0
                        self.player.video_pan_y = min(1.0, current_pan_y + pan_speed)
                    except Exception as e:
                        print(f"Pan up error: {e}")

                elif key == Qt.Key.Key_Down:
                    try:
                        current_pan_y = self.player.video_pan_y or 0.0
                        self.player.video_pan_y = max(-1.0, current_pan_y - pan_speed)
                    except Exception as e:
                        print(f"Pan down error: {e}")
            else:
                # Not zoomed in enough to pan
                print(f"Zoom is {current_zoom}% - zoom in more to pan (needs to be > 100%)")
        
            # IMPORTANT: Accept the event so it doesn't propagate
            event.accept()
            return  # Exit early - don't process as any other key
    
        # No modifier keys below this line
        # Left/Right arrows = Seek video
        if key == Qt.Key.Key_Left:
            if self.player.time_pos:
                self.player.seek(-5, reference='relative')
    
        elif key == Qt.Key.Key_Right:
            if self.player.time_pos:
                self.player.seek(5, reference='relative')
    
        # Up/Down arrows = Zoom in/out (NO ALT modifier)
        elif key == Qt.Key.Key_Up:
            current_zoom = self.zoom_spinbox.value()
            self.zoom_spinbox.setValue(min(1000, current_zoom + 10))
    
        elif key == Qt.Key.Key_Down:
            current_zoom = self.zoom_spinbox.value()
            self.zoom_spinbox.setValue(max(50, current_zoom - 10))
    
        # Spacebar = Play/Pause
        elif key == Qt.Key.Key_Space:
            self.toggle_play_pause()
    
        # I = Mark In
        elif key == Qt.Key.Key_I:
            self.mark_in()
    
        # O = Mark Out
        elif key == Qt.Key.Key_O:
            self.mark_out()
    
        # R = Replay Section
        elif key == Qt.Key.Key_R:
            self.replay_section()

        # S = Screenshot
        elif key == Qt.Key.Key_S:
            self.take_screenshot()

        else:
            super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self.zoom_overlay.hide()
            self.zoom_overlay.cancel()
        else:
            super().keyReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'zoom_overlay'):
            self.zoom_overlay.setGeometry(self.video_widget.rect())

    def closeEvent(self, event):
        """Properly cleanup when closing the application"""
        try:
            # Save recent files before closing
            self.save_recent_files()
            
            # Stop the progress update timer first
            if hasattr(self, 'timer'):
                self.timer.stop()
            
            # Stop playback
            if hasattr(self, 'player'):
                try:
                    self.player.command('stop')
                except:
                    pass
                
                # Terminate the player
                try:
                    self.player.terminate()
                except:
                    pass
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        event.accept()


if __name__ == '__main__':
    # mpv can only embed into a Qt widget via an X11 window id; native Wayland breaks the layout
    if sys.platform.startswith('linux'):
        os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
    app = QApplication(sys.argv)
    # mpv requires a C numeric locale; QApplication resets it on Linux, so set it afterwards
    locale.setlocale(locale.LC_NUMERIC, 'C')
    player = VideoPlayer()
    player.show()
    if len(sys.argv) > 1:
        player.load_video(sys.argv[1])
    sys.exit(app.exec())