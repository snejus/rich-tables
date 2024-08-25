from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta
from functools import singledispatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Iterator, List, Tuple

from rich.bar import Bar
from rich.columns import Columns
from rich.traceback import install
from typing_extensions import TypedDict

from . import task
from .fields import get_val
from .generic import flexitable
from .github import pulls_table
from .music import albums_table
from .utils import (
    border_panel,
    group_by,
    make_console,
    new_table,
    predictably_random_color,
    pretty_diff,
    wrap,
)

if TYPE_CHECKING:
    from rich.console import RenderableType
    from rich.table import Table

JSONDict = Dict[str, Any]


console = make_console()
install(console=console, show_locals=True, width=console.width)


def lights_table(lights: List[JSONDict], **__) -> Iterator[Table]:
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


def calendar_table(events: List[JSONDict], **__) -> Iterable[RenderableType]:
    def get_start_end(start: datetime, end: datetime) -> Tuple[int, int]:
        if start.hour == end.hour == 0:
            return 0, 86400
        day_start_ts = start.replace(hour=0).timestamp()
        return int(start.timestamp() - day_start_ts), int(
            end.timestamp() - day_start_ts
        )

    status_map = {
        "needsAction": "[b grey3] ? [/]",
        "accepted": "[b green] ✔ [/]",
        "declined": "[b red] ✖ [/]",
        "tentative": "[b yellow] ? [/]",
    }

    cal_to_color = {e["calendar"]: e["backgroundColor"] for e in events}
    if len(cal_to_color) > 1:
        color_key = "calendar"
        color_id_to_color = cal_to_color
    else:
        color_key = "colorId"
        color_id_to_color = {
            e[color_key]: predictably_random_color(e[color_key]) for e in events
        }
    for e in events:
        e["color"] = color_id_to_color[e[color_key]]
    cal_fmted = [wrap(f" {c} ", f"b black on {clr}") for c, clr in cal_to_color.items()]
    yield Columns(cal_fmted, expand=True, equal=False, align="center")

    new_events: List[JSONDict] = []
    for event in events:
        start_iso, end_iso = event["start"], event["end"]
        orig_start = datetime.fromisoformat(
            (start_iso.get("dateTime") or start_iso.get("date")).strip("Z")
        )
        orig_end = datetime.fromisoformat(
            (end_iso.get("dateTime") or end_iso.get("date")).strip("Z")
        )
        h_after_midnight = (
            24 * (orig_end - orig_start).days
            + ((orig_end - orig_start).seconds // 3600)
        ) - (24 - orig_start.hour)

        end = (orig_start + timedelta(days=1)).replace(hour=0, minute=0, second=0)

        def eod(day_offset: int) -> datetime:
            return (orig_start + timedelta(days=day_offset)).replace(
                hour=23, minute=59, second=59
            )

        def midnight(day_offset: int) -> datetime:
            return (orig_start + timedelta(days=day_offset)).replace(
                hour=0, minute=0, second=0
            )

        days_count = h_after_midnight // 24 + 1
        for start, end in zip(
            [orig_start, *map(midnight, range(1, days_count + 1))],
            [*map(eod, range(days_count)), orig_end],
        ):
            color = (
                "grey7" if end.replace(tzinfo=None) < datetime.now() else event["color"]
            )
            title = status_map[event["status"]] + wrap(
                event["summary"] or "busy", f"b {color}"
            )
            new_events.append({
                **event,
                "color": color,
                "name": (
                    border_panel(get_val(event, "desc"), title=title)
                    if event["desc"]
                    else title
                ),
                "start": start,
                "start_day": start.strftime("%d %a"),
                "start_time": wrap(start.strftime("%H:%M"), "white"),
                "end_time": wrap(end.strftime("%H:%M"), "white"),
                "desc": (border_panel(get_val(event, "desc")) if event["desc"] else ""),
                "bar": Bar(86400, *get_start_end(start, end), color=color),
                "summary": event["summary"] or "",
            })

    keys = "name", "start_time", "end_time", "bar"
    month_events: Iterable[JSONDict]
    for year_and_month, month_events in group_by(
        new_events, lambda x: x["start"].strftime("%Y %B")
    ):
        table = new_table(*keys, highlight=False, padding=0, show_header=False)
        for day, day_events in group_by(
            month_events, lambda x: x.get("start_day") or ""
        ):
            table.add_row(wrap(day, "b i"))
            for event in day_events:
                if "Week " in event["summary"]:
                    table.add_row("")
                    table.add_dict_item(event, style=event["color"] + " on grey7")
                else:
                    table.add_dict_item(event)
            table.add_row("")
        yield border_panel(table, title=year_and_month)


def load_data(filepath: str) -> list[JSONDict] | JSONDict | str:
    """Load data from the given file.

    Try to load the data as JSON, otherwise return the text as is.
    """
    if filepath == "/dev/stdin":
        text = sys.stdin.read()
    else:
        path = Path(filepath)
        text = path.read_text() if path.exists() and path.is_file() else filepath

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


TABLE_BY_NAME: Dict[str, Callable[..., Any]] = {
    "Pull Requests": pulls_table,
    "Hue lights": lights_table,
    "Calendar": calendar_table,
    "Album": albums_table,
    "Tasks": task.get_table,
}


@singledispatch
def draw_data(data: Any, **kwargs) -> Iterator[RenderableType]:
    """Render the provided data."""
    yield data


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict | NamedData, **kwargs) -> Iterator[RenderableType]:
    if (title := data.get("title")) and (values := data.get("values")):
        table = TABLE_BY_NAME.get(title, flexitable)
        yield from table(values, **kwargs)
    else:
        yield flexitable(data)


@draw_data.register(list)
def _draw_data_list(data: list[JSONDict], **kwargs) -> Iterator[RenderableType]:
    yield flexitable(data)


def main() -> None:
    args = get_args()
    if args.command == "diff":
        console.print(pretty_diff(args.before, args.after))
    else:
        data = load_data("/dev/stdin")
        if args.json:
            console.print_json(data=data)
        else:
            console.record = True
            for renderable in filter(None, draw_data(data, verbose=args.verbose)):
                console.print(renderable)

    if args.save:
        filename = tempfile.NamedTemporaryFile(suffix=".html", delete=False).name
        console.save_html(filename)
        print(f"Saved output as {filename}", file=sys.stderr)


if __name__ == "__main__":
    main()
