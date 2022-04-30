import json
import os

import pytest
from freezegun import freeze_time
from rich_tables.table import draw_data
from rich_tables.utils import make_console
from typing import Iterable

console = make_console(record=True, width=124)


@freeze_time("2022-04-01")
@pytest.mark.parametrize(
    "input_file, output_file",
    [
        ("timed.json", "timed.svg"),
        ("albums.json", "album.svg"),
        ("pr.json", "pr.svg"),
        ("emails.json", "emails.svg"),
    ],
)
def test_pulls(input_file, output_file):
    with open(os.path.join("tests/json", input_file), "r") as f:
        data = json.load(f)

    result = draw_data(data)
    if isinstance(result, Iterable):
        for res in result:
            console.print(res)
    else:
        console.print(result)
    console.save_svg(os.path.join("svgs", output_file))
