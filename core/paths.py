import platform
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.resolve()
RESULTS = ROOT_DIR / "results"


def get_chrome_profiles_path() -> Path | None:
    system = platform.system()

    if system == "Linux":
        profiles_path = Path.home() / ".config" / "chromium"
    elif system == "Windows":
        profiles_path = Path("C:/") / "1" / "GoogleChromePortable" / "Data" / "profile"
    else:
        return None

    if not profiles_path.exists():
        return None

    return profiles_path

