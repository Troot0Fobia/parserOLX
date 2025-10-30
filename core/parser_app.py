import json
from typing import Any

from textual.app import App

from core.paths import ROOT_DIR
from screens.main_menu import MainMenu


class ParserApp(App):

    def __init__(self):
        super().__init__()
        self.settings = json.loads((ROOT_DIR / "settings.json").read_text())

    def on_mount(self) -> None:
        self.push_screen(MainMenu())

    def closeApp(self) -> None:
        self.saveSettings()

    def getSetting(self, key: str) -> Any:
        return self.settings.get(key, None)

    def changeSettings(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.saveSettings()

    def saveSettings(self) -> None:
        with open(ROOT_DIR / "settings.json", "w") as f:
            json.dump(self.settings, f)

