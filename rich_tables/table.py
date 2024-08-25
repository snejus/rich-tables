from __future__ import annotations

import argparse
import json
import sys
from contextlib import suppress
from datetime import datetime, timedelta
from functools import singledispatch
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Tuple,
    Union,
)

from rich.bar import Bar
from rich.columns import Columns
from rich.traceback import install
from typing_extensions import TypedDict

from . import task
from .fields import FIELDS_MAP, get_val
from .generic import flexitable
from .github import pulls_table
from .music import albums_table
from .utils import (
    border_panel,
    format_string,
    group_by,
    make_console,
    md_panel,
    new_table,
    predictably_random_color,
    wrap,
)

if TYPE_CHECKING:
    from rich.console import RenderableType
    from rich.table import Table

JSONDict = Dict[str, Any]


console = make_console()
install(console=console, show_locals=True, width=console.width)


def lights_table(lights: List[JSONDict], **__) -> Table:
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


def load_data() -> JSONDict | None:
    """Load JSON data from the stdin."""
    if sys.stdin.isatty():
        return None

    text = sys.stdin.read()
    try:
        data: JSONDict = json.loads(text)
        assert data
    except json.JSONDecodeError:
        console.print(format_string(text))
        sys.exit(0)
    except AssertionError:
        sys.exit(0)
    else:
        return data


@singledispatch
def draw_data(data: Union[JSONDict, List[JSONDict]]) -> Any:
    return None


def get_args() -> JSONDict:
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("args", nargs="*", default=[])
    return vars(parser.parse_args())


class NamedData(TypedDict):
    title: str
    values: List[JSONDict]


TABLE_BY_NAME: Dict[str, Callable[..., Any]] = {
    "Pull Requests": pulls_table,
    "Hue lights": lights_table,
    "Calendar": calendar_table,
    "Album": albums_table,
    "Tasks": task.get_table,
}


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict | NamedData) -> Iterator[RenderableType]:
    if (title := data.get("title")) and (values := data.get("values")):
        table = TABLE_BY_NAME.get(title, flexitable)
        yield from table(values, **get_args())
    else:
        yield flexitable(data)


@draw_data.register(list)
def _draw_data_list(data: List[JSONDict]) -> Iterator[RenderableType]:
    yield flexitable(data)


def main() -> None:
    args = []
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])

    if args and args[0] == "diff":
        arguments = args[1:]
        with suppress(json.JSONDecodeError):
            arguments = list(map(json.loads, arguments))

        console.print(FIELDS_MAP["diff"](arguments), highlight=False)
    elif args and args[0] == "md":
        console.print(md_panel(sys.stdin.read().replace(r"\x00", "")))
    else:
        if "-s" in set(args):
            console.record = True

        data = load_data()
        if "-j" in args:
            console.print_json(data=data)
        else:
            for ret in draw_data(data):
                console.print(ret)

        if "-s" in set(args):
            console.save_html("saved.html")


if __name__ == "__main__":
    main()
