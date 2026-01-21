import re
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT_DIR / "demos"
sys.path.insert(0, str(ROOT_DIR))


def _parse_method(text: str) -> str | None:
    match = re.search(r"^METHOD\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]", text, re.MULTILINE)
    return match.group(1) if match else None


def _list_get_methods() -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    for path in sorted(DEMO_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        stem = path.stem
        if "_get" not in stem:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        method = _parse_method(text) or stem
        if "get" not in method:
            continue
        idx = stem.find("_get")
        if idx <= 0:
            continue
        category = stem[:idx]
        categories.setdefault(category, []).append(method)
    for category in categories:
        categories[category] = sorted(set(categories[category]))
    return dict(sorted(categories.items()))


def _format_categories(categories: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for category, methods in categories.items():
        lines.append(f"{category}:")
        for method in methods:
            lines.append(f"  - {method}")
    return "\n".join(lines)


class TestGetMethodsCatalog(unittest.TestCase):
    def test_get_methods_catalog(self) -> None:
        categories = _list_get_methods()
        self.assertTrue(categories)
        print(_format_categories(categories))


if __name__ == "__main__":
    unittest.main()
