from textual.app import ComposeResult
from textual.widgets import Header, Footer, OptionList, Static
from textual.widgets.option_list import Option
from textual.screen import Screen
from rich.pretty import Pretty
from rich.panel import Panel

from screens.profiles_screen import ProfilesScreen
from screens.parser_screen import ParserScreen


class MainMenu(Screen):
    def __init__(self):
        super().__init__()
        self.working_profiles = self.app.getSetting('profiles')
        self.panel = Panel(Pretty(self.working_profiles), title="Активные профили")


    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(self.panel, id="active-profiles")
        yield OptionList(
            Option("1. Управлять профилями", id="change_profiles"),
            Option("2. Начать парсинг", id="start_parsing"),
            Option("0. Выйти", id="exit"),
            name="menu"
        )
        yield Footer()

    
    def on_screen_resume(self):
        self.working_profiles = self.app.getSetting('profiles')
        self.query_one("#active-profiles", Static).update(
            Panel(Pretty(self.working_profiles), title="Активные профили")
        )


    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        selected_id = event.option_id
        if selected_id == 'change_profiles':
            self.app.push_screen(ProfilesScreen())
        elif selected_id == 'start_parsing':
            self.app.push_screen(ParserScreen())
        elif selected_id == 'exit':
            self.call_later(self.app.closeApp)
            self.app.exit()
    