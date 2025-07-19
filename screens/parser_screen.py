from textual.screen import ModalScreen, Screen
from textual.widgets import Header, Footer, Input, Static, RichLog, Button, Label
from textual.containers import Container, Grid
from core.parser import Parser
from threading import Thread
import datetime
import csv
import tzlocal
import pyperclip
import asyncio

from core.paths import RESULTS, ROOT_DIR


class StopParsingScreen(ModalScreen[bool]):
    CSS = """
        StopParsingScreen {
            align: center middle;
        }

        #dialog {
            grid-size: 2;
            grid-gutter: 1 2;
            grid-rows: 1fr 3;
            padding: 0 1;
            width: 60;
            height: 11;
            border: thick $background 80%;
            background: $surface;
        }

        #question {
            column-span: 2;
            height: 1fr;
            width: 1fr;
            content-align: center middle;
        }

        Button {
            width: 100%;
        }
    """


    def compose(self):
        yield Grid(
            Label("Действительно завершить парсинг?", id="question"),
            Button("Завершить", variant="success", id='finish'),
            Button("Отмена", variant="error", id="cancel"),
            id="dialog"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'finish':
            self.dismiss(True)
        else:
            self.dismiss(False)


class ParserScreen(Screen):
    CSS = """
        #export-button {
            background: green;
            padding: 0;
            margin: 1;
            color: white;
            width: 100%;
            align: center middle;
        }
    """


    def __init__(self):
        super().__init__()
        self.parser = Parser(self.app)
        self.data = []
        self.proceed = False


    def compose(self):
        yield Header(show_clock=True)
        if (ROOT_DIR / 'state.json').exists():
            data = (ROOT_DIR / 'state.json').read_text()
            yield Label(f"Есть сохраненнные данные, продолжить? \n{data}", id="proceed-question")
            yield Button("Да", variant="success", id="proceed")
        yield Container(
            Input(
                placeholder="Вставьте поисковую ссылку...",
                compact=True,
                validate_on=["submitted"],
                id="input-link"
            ),
            id="main-container")
        yield Footer()


    def on_input_submitted(self, event: Input.Submitted):
        url = event.value
        self.start_paring(url)


    def start_paring(self, url):
        container = self.query_one("#main-container", Container)
        container.query_children('#input-link').remove()
        
        container.mount(Static(f"[bold green]URL:[/bold green] {url}"))
        self.query_one('#proceed').remove()
        self.query_one("#proceed-question").remove()
        container.mount(RichLog(id="log-output", markup=True))
        container.mount(Button("Экспорт в CSV", id="export-button"))
        t = Thread(target=self._parser_task, args=(url,), daemon=True)
        t.start()


    def _parser_task(self, url):
        self.parser.start(url, self.add_log_output, self.add_data, self.proceed)


    def add_data(self, data: dict) -> None:
        self.data.append(data)
        if len(self.data) % 15:
            self.save_data()

    
    def add_log_output(self, text: str, log_type: int = 1):
        style = "green" if log_type == 1 else "red"
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.app.call_from_thread(
            lambda: self.query_one("#log-output", RichLog)
                .write(f"[dim]{timestamp}[/] [{style}]{text.strip()}[/{style}]")
        )


    def log_ended(self):
        self.query_one("#export-button", Button).disabled = False


    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'export-button':
            self.save_data()
        elif event.button.id == "proceed":
            self.proceed = True
            self.start_paring(None)


    def save_data(self):
        if not RESULTS.exists():
            RESULTS.mkdir(parents=True, exist_ok=True)

        filename = RESULTS / f'export_{datetime.datetime.now().astimezone(tzlocal.get_localzone()).strftime("%d.%m.%Y_%H_%M_%S")}.csv'
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=[
                "Имя продавца", "Номер телефона", "Ссылка профиля", "Город", "Регион"
            ])
            writer.writeheader()
            for user_data in self.data:
                writer.writerow({
                    "Имя продавца": user_data.get('username', ''),
                    "Номер телефона": user_data.get('phone', ''),
                    "Ссылка профиля": user_data.get('profile_link', ''),
                    "Город": user_data.get('city', ''),
                    "Регион": user_data.get('region', '')
                })
        
        self.query_one("#log-output", RichLog).write(f"[dim]{datetime.datetime.now().strftime("%H:%M:%S")}[/] [green]Файл сохранен по пути [cyan]{filename}[/cyan][/green]")


    def on_key(self, event):
        if event.key == "ctrl+v":
            text = pyperclip.paste()
            input_widget = self.query_one('#input-link', Input)
            if input_widget is not None:
                input_widget.value = text
        if event.key == 'escape' and self.parser._running:
            def check_quit(finish: bool | None) -> None:
                if finish:
                    self.parser.close()
                    self.log_ended()

            self.app.push_screen(StopParsingScreen(), check_quit)

        elif event.key == 'q':
            self.parser.close()
            self.app.pop_screen()
