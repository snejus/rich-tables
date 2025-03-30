#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import contextmanager
from functools import singledispatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from rich.traceback import install
from typing_extensions import TypedDict

from . import calendar, task
from .diff import pretty_diff
from .fields import get_val
from .generic import flexitable
from .github import pulls_table
from .music import albums_table
from .utils import make_console, new_table, wrap

if TYPE_CHECKING:
    from collections.abc import Iterator

    from rich.console import RenderableType
    from rich.table import Table

MAX_FILENAME_LEN = 255
JSONDict = dict[str, Any]


console = make_console()
install(console=console, show_locals=True, width=console.width)


def lights_table(lights: list[JSONDict], **__: Any) -> Iterator[Table]:
    from rgbxy import Converter

    headers = lights[0].keys()
    table = new_table(*headers)
    conv = Converter()
    for light in lights:
        xy = light.get("xy")
        style = ""
        if not light["on"]:
            style = "dim"
            light["xy"] = ""
        elif xy:
            color = conv.xy_to_hex(*xy)
            light["xy"] = wrap("   a", f"#{color} on #{color}")
        table.add_row(*(get_val(light, h) for h in headers), style=style)
    yield table


def load_data(filepath: str) -> list[JSONDict] | JSONDict | str:
    """Load data from the given file.

    Try to load the data as JSON, otherwise return the text as is.
    """
    if filepath == "/dev/stdin":
        text = sys.stdin.read()
    elif len(filepath) > MAX_FILENAME_LEN or len(filepath.encode()) > MAX_FILENAME_LEN:
        text = filepath
    else:
        path = Path(filepath)
        text = path.read_text() if path.is_file() else filepath

    try:
        json_data: JSONDict | list[JSONDict] = json.loads(text)
    except json.JSONDecodeError:
        return text
    else:
        return json_data


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="""Pretty-print JSON data.
By default, read JSON data from stdin and prettify it.
Otherwise, use command 'diff' to compare two JSON objects or blocks of text.""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-j", "--json", action="store_true", help="output as JSON")
    parser.add_argument(
        "-s", "--save", action="store_true", help="save the output as HTML"
    )

    subparsers = parser.add_subparsers(
        dest="command", title="Subcommands", required=False
    )
    diff_parser = subparsers.add_parser("diff", help="show diff between two objects")
    diff_parser.add_argument(
        "before", type=load_data, help="JSON object or text before, can be a filename"
    )
    diff_parser.add_argument(
        "after", type=load_data, help="JSON object or text after, can be a filename"
    )
    return parser.parse_args()


class NamedData(TypedDict):
    title: str
    values: list[JSONDict]


TABLE_BY_NAME: dict[str, Callable[..., Any]] = {
    "Pull Requests": pulls_table,
    "Hue lights": lights_table,
    "Calendar": calendar.get_table,
    "Album": albums_table,
    "Tasks": task.get_table,
}


@singledispatch
def draw_data(data: Any, **kwargs: Any) -> Iterator[RenderableType]:
    """Render the provided data."""
    yield data


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict | NamedData, **kwargs: Any) -> None:
    if (title := data.get("title")) and (values := data.get("values")):
        table = TABLE_BY_NAME.get(title, flexitable)
        for renderable in table(values, **kwargs):
            console.print(renderable)
    else:
        console.print(flexitable(data))


@draw_data.register(list)
def _draw_data_list(data: list[JSONDict], **__: Any) -> None:
    console.print(flexitable(data))


@contextmanager
def handle_save(save: bool) -> Iterator[None]:
    if save:
        yield

        if save:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as file:
                filename = file.name
            console.save_html(filename)
            print(f"Saved output as {filename}", file=sys.stderr)
    else:
        yield


def main() -> None:
    args = get_args()

    with handle_save(args.save):
        if args.command == "diff":
            console.print(pretty_diff(args.before, args.after), markup=False)
        else:
            data = load_data("/dev/stdin")
            if args.json:
                console.print_json(data=data)
            elif data:
                draw_data(data, verbose=args.verbose)


if __name__ == "__main__":
    main()
