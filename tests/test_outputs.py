import json
import os

import pytest
from rich.traceback import install
from rich_tables.music import make_albums_table
from rich_tables.table import make_counts_table, make_pulls_table, draw_data
from rich_tables.utils import make_console

# install(show_locals=True, extra_lines=8, width=int(os.environ.get("COLUMNS", 150)))
console = make_console(record=True, width=int(os.environ.get("COLUMNS", 150) - 10))


def test_pulls():
    with open("tests/json/pr_data.json", "r") as f:
        data = json.load(f)

    result = make_pulls_table(data["values"])
    console.print(result)

    console.save_svg("results.svg")
    pytest.fail()


def test_time():
    with open("tests/json/timed.json", "r") as f:
        data = json.load(f)

    result = make_counts_table(data)
    console.print(result)

    console.save_svg("results.svg")
    pytest.fail()


def test_album():
    with open("tests/json/albums.json", "r") as f:
        data = json.load(f)

    result = make_albums_table(data["values"])
    # result = draw_data(data)
    console.print(result)

    console.save_svg("svgs/album.svg")
    pytest.fail()
