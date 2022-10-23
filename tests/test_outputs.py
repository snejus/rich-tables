import json
import os
from typing import Iterable

import pytest
from freezegun import freeze_time

from rich_tables.table import draw_data
from rich_tables.utils import make_console

JSON_DIR = "tests/json"
SVG_DIR = "svgs"
TEST_CASES = [x.replace(".json", "") for x in os.listdir(JSON_DIR)]


@pytest.fixture(scope="session", autouse=True)
def report():
    yield

    toc = [f"* [{x.replace('_', ' ').capitalize()}](#{x})\n" for x in TEST_CASES]
    svgs = [f"## {x.capitalize()}\n![image](svgs/{x}.svg)\n" for x in TEST_CASES]

    with open("README.md", "w") as f:
        f.writelines(["# Rich tables\n\n", *toc, "\n\n", *svgs])


@freeze_time("2022-04-01")
@pytest.mark.parametrize("testcase", TEST_CASES)
def test_pulls(testcase):
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
