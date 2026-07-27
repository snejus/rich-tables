from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from freezegun import freeze_time
from rich.console import CONSOLE_SVG_FORMAT  # type: ignore[attr-defined]

from rich_tables import table
from rich_tables.utils import make_console

if TYPE_CHECKING:
    from collections.abc import Iterator

JSON_DIR = Path("tests/json")
SVG_DIR = Path("svgs")
TEST_FILES = sorted(JSON_DIR.glob("*.json"))

IOSEVKA_SVG_FORMAT = (
    CONSOLE_SVG_FORMAT.replace(
        """@font-face {{
        font-family: "Fira Code";
        src: local("FiraCode-Regular"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff2/FiraCode-Regular.woff2") format("woff2"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff/FiraCode-Regular.woff") format("woff");
        font-style: normal;
        font-weight: 400;
    }}""",  # noqa: E501
        """@font-face {{
        font-family: "Iosevka Nerd Font";
        src: local("Iosevka Nerd Font"),
             local("Iosevka NF");
        font-style: normal;
        font-weight: 400;
    }}""",
    )
    .replace(
        """@font-face {{
        font-family: "Fira Code";
        src: local("FiraCode-Bold"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff2/FiraCode-Bold.woff2") format("woff2"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff/FiraCode-Bold.woff") format("woff");
        font-style: bold;
        font-weight: 700;
    }}""",  # noqa: E501
        """@font-face {{
        font-family: "Iosevka Nerd Font";
        src: local("Iosevka Nerd Font Bold"),
             local("Iosevka NF Bold");
        font-style: normal;
        font-weight: 700;
    }}""",
    )
    .replace(
        "font-family: Fira Code, monospace;",
        'font-family: "Iosevka Nerd Font", monospace;',
    )
)


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
    sys.argv[1:] = ["-v"]

    table.console = make_console(record=True, width=156)  # type: ignore[attr-defined]
    table.main()
    table.console.save_svg(  # type: ignore[attr-defined]
        str(SVG_DIR / f"{testcase.stem}.svg"),
        code_format=IOSEVKA_SVG_FORMAT,
        font_aspect_ratio=0.5,
    )
