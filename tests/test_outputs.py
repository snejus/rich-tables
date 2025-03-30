import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from freezegun import freeze_time

from rich_tables import table
from rich_tables.utils import make_console

JSON_DIR = Path("tests/json")
SVG_DIR = Path("svgs")
TEST_FILES = sorted(JSON_DIR.glob("*.json"))


def human(text: str) -> str:
    return text.replace("_", " ").capitalize().replace("json", "JSON")


@pytest.fixture(scope="session", autouse=True)
def _populate_readme() -> Iterator[None]:
    yield

    svgs = "\n\n".join(
        f"""### {human(f.stem)}

![image]({SVG_DIR / f"{f.stem}.svg"})"""
        for f in TEST_FILES
    )

    readme_path = Path("README.md")
    readme = readme_path.read_text()
    readme = re.sub(r"(?<=## Examples\n\n).*", svgs, readme, flags=re.S)
    readme_path.write_text(readme)


@freeze_time("2022-04-01")
@pytest.mark.parametrize("testcase", TEST_FILES, ids=str)
def test_outputs(testcase: Path) -> None:
    sys.stdin = testcase.open()
    sys.argv[1:] = []

    table.console = make_console(record=True, width=156)
    table.main()
    table.console.save_svg(str(SVG_DIR / f"{testcase.stem}.svg"))
