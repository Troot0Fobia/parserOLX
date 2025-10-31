import json
from dataclasses import asdict, dataclass, field

from .paths import ROOT_DIR

STATE_FILE = ROOT_DIR / "state.json"


@dataclass
class ParserState:
    url: str = ""
    cards: list[str] = field(default_factory=list)


def load_state() -> ParserState:
    if not STATE_FILE.exists():
        return ParserState()

    return ParserState(**(json.loads(STATE_FILE.read_text())))


def save_state(state: ParserState) -> None:
    STATE_FILE.write_text(json.dumps(asdict(state), ensure_ascii=True))


def is_data_exists() -> dict | None:
    if not STATE_FILE.exists():
        return None

    data = json.loads(STATE_FILE.read_text())
    if data["cards"]:
        return data

    return None
