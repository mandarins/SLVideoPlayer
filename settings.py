# settings.py
import json
import os
from pathlib import Path

SETTINGS_PATH = "settings.json"


class Settings:
    """Persists user preferences to settings.json"""

    def __init__(self):
        self.download_folder = str(Path.home() / "Downloads")
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, 'r') as f:
                self.download_folder = json.load(f).get("download_folder", self.download_folder)

    def get_download_folder(self):
        # Screenshots are written straight into this folder, so it must exist
        os.makedirs(self.download_folder, exist_ok=True)
        return self.download_folder

    def set_download_folder(self, folder):
        self.download_folder = folder
        with open(SETTINGS_PATH, 'w') as f:
            json.dump({"download_folder": folder}, f, indent=2)
