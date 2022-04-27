import json
import os

import pytest
from freezegun import freeze_time
from rich_tables.table import draw_data
from rich_tables.utils import make_console

console = make_console(record=True, width=124)


@freeze_time("2022-04-01")
@pytest.mark.parametrize(
    "input_file, output_file",
    [
        ("pr_data.json", "pulls.svg"),
        ("timed.json", "timed.svg"),
        ("albums.json", "album.svg"),
        ("pr.json", "pr.svg"),
    ],
)
def test_pulls(input_file, output_file):
    with open(os.path.join("tests/json", input_file), "r") as f:
        data = json.load(f)

    result = draw_data(data)
    console.print(result)
    console.save_svg(os.path.join("svgs", output_file))
