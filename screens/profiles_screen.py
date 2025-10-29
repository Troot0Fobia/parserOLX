import platform
from pathlib import Path

from rich.rule import Rule
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Header, Static


class ProfilesScreen(ModalScreen):
    CSS = """
        #buttons {
            align-horizontal: center;
            padding: 0;
        }

        #profile-scroll {
            height: auto;
            padding: 0;
            margin-bottom: 1;
        }

        .checkbox {
            width: 100%;
            padding: 0 1;
        }
    """

    def __init__(self):
        super().__init__()
        self.profile_checkboxes = []
        self.active_profiles = self.app.getSetting("profiles")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(Rule("Профили Chrome"), shrink=True)

        with VerticalScroll(id="profile-scroll"):
            for profile, path in self.get_chrome_profiles().items():
                cb = Checkbox(
                    profile,
                    value=True if profile in self.active_profiles else False,
                    name=str(path),
                    classes="checkbox",
                )
                self.profile_checkboxes.append(cb)
                yield cb

        with Horizontal(id="buttons"):
            yield Button("Сохранить", id="save", variant="success")
            yield Button("Отмена", id="cancel", variant="error")

        yield Footer()

    def on_mount(self):
        if self.profile_checkboxes:
            self.profile_checkboxes[0].focus()

    def on_key(self, event):
        if event.key in ("escape", "q"):
            self.app.pop_screen()
            return

        focused = self.focused
        if event.key in ("down", "up"):
            widgets = self.profile_checkboxes + [
                self.query_one("#save"),
                self.query_one("#cancel"),
            ]
            if focused in widgets:
                idx = widgets.index(focused)
                if event.key == "down":
                    idx = (idx + 1) % len(widgets)
                elif event.key == "up":
                    idx = (idx - 1) % len(widgets)
                self.set_focus(widgets[idx])

    def get_chrome_profiles(self):
        system = platform.system()
        home_dir = Path.home()
        profiles_path = None
        profiles = {}

        if system == "Linux":
            profiles_path = home_dir / ".config" / "chromium"
        elif system == "Windows":
            profiles_path = (
                Path("C:/") / "1" / "GoogleChromePortable" / "Data" / "profile"
            )
        else:
            return {}

        if not profiles_path.exists():
            return {}

        for folder in profiles_path.iterdir():
            if folder.is_dir():
                for root_folder, _, files in folder.walk():
                    if "History" in files:
                        profiles[root_folder.name] = root_folder
                        break

        return dict(sorted(profiles.items()))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "save":
            selected_profiles = {
                str(cb.label): Path(cb.name)
                for cb in self.profile_checkboxes
                if cb.value
            }
            print(f"Chosen profiles: {selected_profiles}")
            self.app.changeSettings("profiles", list(selected_profiles.keys()))
            self.app.pop_screen()

