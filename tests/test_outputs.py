import re
import sys
from pathlib import Path
from typing import Iterator

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

    with Path("README.md").open("r+") as f:
        readme = f.read()
        f.seek(0)
        readme = re.sub(r"(?<=## Examples\n\n).*", svgs, readme, flags=re.S)
        f.write(readme)


@freeze_time("2022-04-01")
@pytest.mark.parametrize("testcase", TEST_FILES, ids=str)
def test_outputs(testcase: Path) -> None:
    sys.stdin = testcase.open()

    table.console = make_console(record=True, width=156)
    table.main()
    table.console.save_svg(str(SVG_DIR / f"{testcase.stem}.svg"))
