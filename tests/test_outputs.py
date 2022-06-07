import json
import os
from typing import Iterable

import pytest
from freezegun import freeze_time

from rich_tables.table import draw_data
from rich_tables.utils import make_console


@freeze_time("2022-04-01")
@pytest.mark.parametrize("testcase", ["timed", "album", "pr", "emails", "generic"])
def test_pulls(testcase):
    with open(os.path.join("tests/json", f"{testcase}.json"), "r") as f:
        data = json.load(f)

    console = make_console(record=True)
    result = draw_data(data)
    if isinstance(result, Iterable):
        for res in result:
            console.print(res)
    else:
        console.print(result)
    console.save_svg(os.path.join("svgs", f"{testcase}.svg"))
