# settings_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFileDialog, QDialogButtonBox)


class SettingsDialog(QDialog):
    """Dialog for editing the screenshot download folder"""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Download folder for screenshots:"))

        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit(settings.download_folder)
        folder_layout.addWidget(self.folder_edit)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(browse_button)
        layout.addLayout(folder_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def accept(self):
        self.settings.set_download_folder(self.folder_edit.text())
        super().accept()
