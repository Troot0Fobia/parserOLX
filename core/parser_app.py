import json

from textual.app import App

from core.paths import ROOT_DIR
from screens.main_menu import MainMenu


class ParserApp(App):

    def __init__(self):
        super().__init__()
        self.settings = json.loads((ROOT_DIR / "settings.json").read_text())

    def on_mount(self):
        self.push_screen(MainMenu())

    async def closeApp(self):
        with open(ROOT_DIR / "settings.json", "w") as f:
            json.dump(self.settings, f)

    def getSetting(self, key):
        return self.settings.get(key, None)

    def changeSettings(self, key, value):
        self.settings[key] = value

