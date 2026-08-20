from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def read_home_html() -> str:
    """Load the home page template from disk."""
    return (TEMPLATES_DIR / "home.html").read_text(encoding="utf-8")
