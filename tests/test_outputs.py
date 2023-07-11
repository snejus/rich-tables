import json
import os
import re
from typing import Iterable

import pytest
from freezegun import freeze_time

from rich_tables.table import draw_data
from rich_tables.utils import make_console

JSON_DIR = "tests/json"
SVG_DIR = "svgs"
TEST_CASES = sorted([x.replace(".json", "") for x in os.listdir(JSON_DIR)])


def human(text: str) -> str:
    return text.replace("_", " ").capitalize().replace("json", "JSON")


@pytest.fixture(scope="session", autouse=True)
def populate_readme():
    yield

    svgs = "\n\n".join(f"### {human(x)}\n\n![image](svgs/{x}.svg)" for x in TEST_CASES)

    with open("README.md") as f:
        readme = f.read()

    readme = re.sub(r"(## Examples.).*", rf"\1{svgs}", readme, flags=re.M | re.S)

    with open("README.md", "w") as f:
        f.write(readme)


@freeze_time("2022-04-01")
@pytest.mark.parametrize("testcase", TEST_CASES)
def test_outputs(testcase):
    with open(os.path.join(JSON_DIR, f"{testcase}.json"), "r") as f:
        data = json.load(f)

    console = make_console(record=True, width=156)
    result = draw_data(data)
    if isinstance(result, Iterable):
        for res in result:
            console.print(res)
    else:
        console.print(result)
    console.save_svg(os.path.join(SVG_DIR, f"{testcase}.svg"))
