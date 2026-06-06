#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager, nullcontext, suppress
from datetime import datetime, timezone
from functools import singledispatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from rich.align import Align
from rich.console import Console
from rich.markup import escape as escape_markup
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.traceback import install
from typing_extensions import TypedDict

from . import calendar, task
from .diff import pretty_diff
from .fields import get_val
from .generic import flexitable
from .github import pulls_table
from .music import albums_table
from .utils import console, new_table, wrap

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from rich.table import Table

MAX_FILENAME_LEN = 255
JSONDict = dict[str, Any]


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
        # attach terminal because Console.pager uses pydoc which won't page when either
        # stdin or stdout is not a terminal
        with suppress(OSError):
            sys.stdin = Path("/dev/tty").open()  # noqa: SIM115
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
    parser.add_argument(
        "-p", "--pager", action="store_true", help="use pager for output"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-j", "--json", action="store_true", help="output as JSON")
    parser.add_argument(
        "-o", "--output-file", type=Path, help="save as SVG to provided file"
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
def draw_data(data: Any, **kwargs: Any) -> None:
    """Render the provided data."""
    console.print(data)


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
    if data:
        console.print(flexitable(data))


@contextmanager
def handle_save(output_file: Path | None) -> Iterator[None]:
    if output_file:
        console.record = True

    yield

    if output_file:
        console.save_svg(str(output_file))


console = Console()


def parse_iso(ts: str) -> datetime:
    # Your timestamps are like "2026-06-01T06:30:42Z"
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def rel_age(created_at: str) -> str:
    dt = parse_iso(created_at)
    delta = datetime.now(timezone.utc) - dt
    days = delta.days
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def last_comment_summary(last_comment: Mapping[str, Any] | None) -> str:
    if not last_comment:
        return "no comments"
    author = last_comment["author"]
    when = rel_age(last_comment["created_at"])
    snippet = last_comment["body"].splitlines()[0].strip()
    if len(snippet) > 80:
        snippet = snippet[:77] + "…"
    return f"{author} · {when}\n[dim]{escape_markup(snippet)}[/dim]"


def labels_summary(labels: Sequence[Mapping[str, Any]]) -> str:
    if not labels:
        return "none"
    # keep it simple; you could colorize based on label["color"] if you want
    return ", ".join(label["name"] for label in labels)


def make_pr_card(pr: Mapping[str, Any], *, highlight: bool = False) -> Panel:
    title = Text(pr["title"], style="bold")
    # GitHub-style URL markup → Rich link markup
    url = pr["url"].removeprefix("[url]").removesuffix("[/url]")
    link_line = f"[link={url}]{url}[/link]"

    state = pr["state"]
    plus_minus = pr["+/-"]
    author = pr["author"]
    labels = labels_summary(pr["labels"])
    issue_ref = pr.get(" ", "") or "—"

    body_lines = [
        f"[dim]{state}[/dim] {plus_minus}",
        f"[bold]Author:[/bold] {author}",
        f"[bold]Labels:[/bold] {escape_markup(labels)}",
        f"[bold]Issue:[/bold] {escape_markup(issue_ref)}",
        "",
        f"[bold]Last comment:[/bold]",
        last_comment_summary(pr.get("last_comment")),
        "",
        link_line,
    ]
    body = Align.left(Text.from_markup("\n".join(body_lines)))

    border_style = "magenta" if highlight else "cyan"
    return Panel(body, title=title, border_style=border_style, padding=(1, 2))


def show_pr_dashboard(data: Mapping[str, Any]) -> None:
    need_resp: list[Mapping[str, Any]] = data["need_my_response"]
    the_rest: list[Mapping[str, Any]] = data["the_rest"]

    layout = Table.grid(padding=(0, 1))
    # Two columns; tweak ratios if you want one column to be wider
    layout.add_column(ratio=1)
    layout.add_column(ratio=1)

    # First row: cards that need your response, highlighted
    left_cards = [make_pr_card(pr, highlight=True) for pr in need_resp]
    right_cards = [make_pr_card(pr) for pr in the_rest[: len(left_cards)]]

    # Zip longest so both columns fill; pad with empty cells if uneven
    max_len = max(len(left_cards), len(right_cards))
    left_cards += [""] * (max_len - len(left_cards))
    right_cards += [""] * (max_len - len(right_cards))

    for left, right in zip(left_cards, right_cards):
        layout.add_row(left, right)

    console.print(layout)


def main() -> None:
    args = get_args()

    with (
        console.pager(styles=True) if args.pager else nullcontext(),
        handle_save(args.output_file),
    ):
        if args.command == "diff":
            console.print(pretty_diff(args.before, args.after), highlight=False)
        else:
            data = load_data("/dev/stdin")
            return show_pr_dashboard(data)
            if args.json:
                console.print_json(data=data)
            elif data:
                draw_data(data, verbose=args.verbose)


if __name__ == "__main__":
    main()
