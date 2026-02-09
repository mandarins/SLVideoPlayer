# recent_files_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QListWidget, QLabel, QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
import os

class RecentFilesDialog(QDialog):
    """Dialog for viewing and selecting recent files"""
    
    # Signal emitted when user wants to open a file
    file_selected = pyqtSignal(str)
    
    def __init__(self, recent_files, parent=None):
        super().__init__(parent)
        self.recent_files = recent_files
        self.setWindowTitle("Recent Files")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self.init_ui()
        self.populate_list()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Double-click to open a recent file:")
        layout.addWidget(info_label)
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.list_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        open_button = QPushButton("Open Selected")
        open_button.clicked.connect(self.on_open_clicked)
        button_layout.addWidget(open_button)
        
        clear_button = QPushButton("Clear History")
        clear_button.clicked.connect(self.on_clear_clicked)
        button_layout.addWidget(clear_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def populate_list(self):
        """Populate the list with recent files"""
        self.list_widget.clear()
        
        if not self.recent_files:
            item = QListWidgetItem("No recent files")
            item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
            self.list_widget.addItem(item)
            return
        
        for file_path in self.recent_files:
            # Check if file still exists
            exists = os.path.exists(file_path)
            
            # Create display text
            file_name = Path(file_path).name
            if exists:
                display_text = f"{file_name}\n    {file_path}"
            else:
                display_text = f"{file_name} [FILE NOT FOUND]\n    {file_path}"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, file_path)  # Store full path
            
            # Gray out missing files
            if not exists:
                item.setForeground(Qt.GlobalColor.gray)
            
            self.list_widget.addItem(item)
    
    def on_item_double_clicked(self, item):
        """Handle double-click on an item"""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path and os.path.exists(file_path):
            self.file_selected.emit(file_path)
            self.close()
        elif file_path:
            QMessageBox.warning(self, "File Not Found", 
                f"The file no longer exists:\n{file_path}")
    
    def on_open_clicked(self):
        """Handle Open button click"""
        current_item = self.list_widget.currentItem()
        if current_item:
            file_path = current_item.data(Qt.ItemDataRole.UserRole)
            if file_path and os.path.exists(file_path):
                self.file_selected.emit(file_path)
                self.close()
            elif file_path:
                QMessageBox.warning(self, "File Not Found", 
                    f"The file no longer exists:\n{file_path}")
    
    def on_clear_clicked(self):
        """Handle Clear History button click"""
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all recent files history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.recent_files.clear()
            self.populate_list()
            QMessageBox.information(self, "Cleared", "Recent files history has been cleared.")
