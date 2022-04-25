import json
import os

import pytest
from rich_tables.music import albums_table
from rich_tables.table import pulls_table
from rich_tables.utils import counts_table, make_console

console = make_console(record=True, width=int(os.environ.get("COLUMNS", 150)) - 10)


def test_pulls():
    with open("tests/json/pr_data.json", "r") as f:
        data = json.load(f)

    result = pulls_table(data["values"])
    console.print(result)

    console.save_svg("results.svg")


def test_time():
    with open("tests/json/timed.json", "r") as f:
        data = json.load(f)

    result = counts_table(data)
    console.print(result)

    console.save_svg("results.svg")


def test_album():
    with open("tests/json/albums.json", "r") as f:
        data = json.load(f)

    result = albums_table(data["values"])
    console.print(result)

    console.save_svg("svgs/album.svg")
