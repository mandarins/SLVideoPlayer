# SLVideoPlayer.py - Main application file
import sys
import os
import locale
import string
import tempfile
import json
from pathlib import Path

# Fix MPV DLL path for Windows
if sys.platform == 'win32':
    # Add current directory to PATH so libmpv-2.dll can be found
    os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ["PATH"]

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QSlider, QLabel, 
                             QFileDialog, QToolBar, QStyle, QMessageBox,
                             QComboBox, QSpinBox, QInputDialog)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QKeySequence
import mpv
from color_dialog import ColorCorrectionDialog
from recent_files_dialog import RecentFilesDialog

# Fix for Windows locale
locale.setlocale(locale.LC_NUMERIC, 'C')

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.bookmarks = []
        self.screenshot_counter = 1  # Sequential counter for screenshots
        self.recent_files = []  # List to store recent files
        self.max_recent_files = 50  # Maximum number of recent files to keep
        self.recent_files_path = "recent_files.json"  # File to save recent files
        
        self.load_recent_files()  # Load recent files from disk
        self.init_ui()
        self.init_player()
        
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
        
        # Controls layout
        controls_layout = QVBoxLayout()
        
        # Progress bar
        progress_layout = QHBoxLayout()
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
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
        self.zoom_spinbox.setRange(50, 300)
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

    def init_player(self):
        try:
            self.player = mpv.MPV(
                wid=str(int(self.video_widget.winId())),
                input_default_bindings=True,
                input_vo_keyboard=True,
                hwdec='auto',
                vo='gpu',
                keep_open='yes',
                loop='no'
            )
            self.player.volume = 50
            self.current_rotation = 0
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to initialize player: {str(e)}\n\nMake sure libmpv-2.dll is in the same folder as this script.")
            sys.exit(1)
    
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
        """Load and play a video file"""
        try:
            self.current_file = file_path
            self.player.play(file_path)
            self.play_button.setText("Pause")
            self.setWindowTitle(f"Video Player - {Path(file_path).name}")
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
        self.player.video_zoom = zoom_factor - 1.0  # MPV uses 0 as 100%
    
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
        """Apply sharpness adjustment to video (using hue as proxy since mpv doesn't have sharpness)"""
        try:
            # MPV doesn't have direct sharpness control
            # We'll use this as a placeholder or implement via video filters
            # For now, just store the value
            if not hasattr(self, 'sharpness_value'):
                self.sharpness_value = 0
            self.sharpness_value = value
        except Exception as e:
            print(f"Error setting sharpness: {e}")

    def reset_color_correction(self):
        """Reset all color correction values"""
        try:
            self.player.brightness = 0
            self.player.contrast = 0
            self.player.saturation = 0
            self.player.gamma = 0
            if hasattr(self, 'sharpness_value'):
                self.sharpness_value = 0
        except Exception as e:
            print(f"Error resetting color correction: {e}")
    
    def update_progress(self):
        """Update the progress bar and time display"""
        try:
            # Check if player is still alive
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
        except Exception:
            # Silently ignore errors (player might be shutting down)
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
        
        # Get the directory where the video is located
        video_dir = os.path.dirname(self.current_file)
        
        # Generate filename with sequential number
        while True:
            filename = f"{base_name}_{self.screenshot_counter:04d}{extension}"
            full_path = os.path.join(video_dir, filename)
            
            # Check if file exists
            if not os.path.exists(full_path):
                return full_path
            
            # If file exists, increment counter and try again
            self.screenshot_counter += 1
    
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
                QMessageBox.warning(self, "Error", "Could not determine save path")
                return
            
            # Check if we're zoomed
            current_zoom = self.zoom_spinbox.value()
            
            if current_zoom == 100:
                # No zoom, simple screenshot
                self.player.screenshot_to_file(save_path)
                self.screenshot_counter += 1
                QMessageBox.information(self, "Success", 
                    f"Screenshot saved to:\n{save_path}\n\n"
                    f"Screenshot #{self.screenshot_counter - 1}")
            else:
                # Zoomed - need to capture the zoomed area
                self.take_zoomed_screenshot(save_path, current_zoom)
                self.screenshot_counter += 1
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to take screenshot: {str(e)}")

    def take_zoomed_screenshot(self, save_path, zoom_percent):
        """Take a screenshot of the zoomed area using video pan/zoom values"""
        try:
            from PIL import Image
            
            # Take a full frame screenshot to temp file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                temp_path = tmp.name
            
            self.player.screenshot_to_file(temp_path)
            
            # Open the full frame
            img = Image.open(temp_path)
            width, height = img.size
            
            # Calculate the visible area based on zoom
            zoom_factor = zoom_percent / 100.0
            
            # Get pan values (MPV video-pan-x and video-pan-y)
            # These determine where the center of the zoomed view is
            try:
                pan_x = self.player.video_pan_x or 0.0
                pan_y = self.player.video_pan_y or 0.0
            except:
                pan_x = 0.0
                pan_y = 0.0
            
            # Calculate the crop rectangle
            # When zoomed in, we see less of the image
            visible_width = width / zoom_factor
            visible_height = height / zoom_factor
            
            # Center point (accounting for pan)
            center_x = (width / 2) + (pan_x * width)
            center_y = (height / 2) + (pan_y * height)
            
            # Calculate crop box
            left = max(0, int(center_x - visible_width / 2))
            top = max(0, int(center_y - visible_height / 2))
            right = min(width, int(center_x + visible_width / 2))
            bottom = min(height, int(center_y + visible_height / 2))
            
            # Crop the image
            cropped = img.crop((left, top, right, bottom))
            
            # Save the cropped image
            cropped.save(save_path)
            
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            
            QMessageBox.information(self, "Success", 
                f"Zoomed screenshot saved to:\n{save_path}\n\n"
                f"Screenshot #{self.screenshot_counter}\n"
                f"Zoom: {zoom_percent}%\n"
                f"Captured area: {right-left}x{bottom-top} pixels")
        
        except ImportError:
            QMessageBox.warning(self, "PIL Required", 
                "The Pillow library is required for zoomed screenshots.\n\n"
                "Install it with: pip install Pillow\n\n"
                "For now, taking a full-frame screenshot...")
            self.player.screenshot_to_file(save_path)
            QMessageBox.information(self, "Success", f"Screenshot saved to:\n{save_path}")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to take zoomed screenshot: {str(e)}")
    
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
    
    def keyPressEvent(self, event):
        # Get modifier keys
        modifiers = event.modifiers()
        
        # Alt + Arrow keys = Pan (when zoomed)
        if modifiers & Qt.KeyboardModifier.AltModifier:
            current_zoom = self.zoom_spinbox.value()
            
            if current_zoom > 100:  # Only pan when zoomed
                pan_speed = 0.05  # Adjust this for faster/slower panning
                
                if event.key() == Qt.Key.Key_Left:
                    # Pan left
                    try:
                        current_pan_x = self.player.video_pan_x or 0.0
                        self.player.video_pan_x = max(-1.0, current_pan_x - pan_speed)
                    except:
                        self.player.video_pan_x = -pan_speed
                    
                elif event.key() == Qt.Key.Key_Right:
                    # Pan right
                    try:
                        current_pan_x = self.player.video_pan_x or 0.0
                        self.player.video_pan_x = min(1.0, current_pan_x + pan_speed)
                    except:
                        self.player.video_pan_x = pan_speed
                    
                elif event.key() == Qt.Key.Key_Up:
                    # Pan up
                    try:
                        current_pan_y = self.player.video_pan_y or 0.0
                        self.player.video_pan_y = max(-1.0, current_pan_y - pan_speed)
                    except:
                        self.player.video_pan_y = -pan_speed
                    
                elif event.key() == Qt.Key.Key_Down:
                    # Pan down
                    try:
                        current_pan_y = self.player.video_pan_y or 0.0
                        self.player.video_pan_y = min(1.0, current_pan_y + pan_speed)
                    except:
                        self.player.video_pan_y = pan_speed
        
        # Regular arrow keys without Alt = Seek video
        elif event.key() == Qt.Key.Key_Left:
            if self.player.time_pos:
                self.player.seek(-5, reference='relative')
        
        elif event.key() == Qt.Key.Key_Right:
            if self.player.time_pos:
                self.player.seek(5, reference='relative')
        
        # Up/Down arrows = Zoom in/out
        elif event.key() == Qt.Key.Key_Up:
            current_zoom = self.zoom_spinbox.value()
            self.zoom_spinbox.setValue(min(300, current_zoom + 10))
        
        elif event.key() == Qt.Key.Key_Down:
            current_zoom = self.zoom_spinbox.value()
            self.zoom_spinbox.setValue(max(50, current_zoom - 10))
        
        # Spacebar = Play/Pause
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play_pause()
        
        # I = Mark In
        elif event.key() == Qt.Key.Key_I:
            self.mark_in()
        
        # O = Mark Out
        elif event.key() == Qt.Key.Key_O:
            self.mark_out()
        
        # R = Replay Section
        elif event.key() == Qt.Key.Key_R:
            self.replay_section()
        
        else:
            super().keyPressEvent(event)
    
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
    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())