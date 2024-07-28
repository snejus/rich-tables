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

from funcy import curry, join
from rich.bar import Bar
from rich.columns import Columns
from rich.traceback import install

from .fields import FIELDS_MAP, get_val
from .generic import flexitable
from .github import pulls_table
from .music import albums_table
from .utils import (
    border_panel,
    format_string,
    format_with_color,
    group_by,
    human_dt,
    make_console,
    md_panel,
    new_table,
    new_tree,
    predictably_random_color,
    wrap,
)

if TYPE_CHECKING:
    from rich.console import ConsoleRenderable
    from rich.panel import Panel
    from rich.table import Table

JSONDict = Dict[str, Any]


@curry
def keep_keys(keys: Iterable[str], item: JSONDict) -> JSONDict:
    return dict(zip(keys, map(item.get, keys)))


console = make_console()
install(console=console, show_locals=True, width=console.width)


def lights_table(lights: List[JSONDict]) -> Table:
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


def calendar_table(events: List[JSONDict]) -> Iterable[ConsoleRenderable]:
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


def tasks_table(tasks_by_group: Dict[str, JSONDict]) -> Iterator[Panel]:
    if not tasks_by_group:
        return

    SKIP_HEADERS = {
        "priority",
        "recur",
        "uuid",
        "reviewed",
        "modified",
        "annotations",
        "depends",
    }
    fields_map: JSONDict = {
        "id": str,
        "uuid": str,
        "urgency": lambda x: str(round(float(x), 1)),
        "description": lambda x: x,
        "due": human_dt,
        "end": human_dt,
        "sched": human_dt,
        "tags": format_with_color,
        "project": format_with_color,
        "modified": human_dt,
        "created": human_dt,
        "start": human_dt,
        "priority": lambda x: wrap(f"({wrap('!', 'red')})", "b") + " "
        if x == "H"
        else "",
        "annotations": lambda ann: new_tree(
            (
                wrap(human_dt(a["created"]), "b") + ": " + wrap(a["description"], "i")
                for a in ann
            ),
            "Annotations",
        )
        if ann
        else None,
    }
    FIELDS_MAP.update(fields_map)

    tasks = join(tasks_by_group.values())
    first_task = tasks[0]

    all_headers = first_task.keys()
    initial_headers = ["id", "urgency", "created", "modified"]
    ordered_keys = dict.fromkeys([*initial_headers, *sorted(all_headers)]).keys()
    valid_keys = [k for k in ordered_keys if k not in SKIP_HEADERS]
    keep_headers = keep_keys(valid_keys)

    status_map = {
        "completed": "b s black on green",
        "deleted": "s red",
        "pending": "white",
        "started": "b green",
        "recurring": "i magenta",
    }

    desc_by_uuid = {}
    for task in tasks:
        desc = task["description"]
        if task.get("recur") and task["status"] != "recurring":
            task["status"] = "recurring"
            desc += f" ({task})"
        elif task.get("start"):
            task["status"] = "started"

        desc = get_val(task, "priority") + wrap(desc, status_map[task["status"]])
        desc = new_tree(title=desc, guide_style="white")
        task["description"] = desc
        desc_by_uuid[task["uuid"]] = desc

    for group, tasks in tasks_by_group.items():
        for task in tasks:
            annotations = get_val(task, "annotations")
            if annotations:
                task["description"].add(annotations)

            dep_uuids = task.get("depends") or []
            deps = list(filter(None, map(desc_by_uuid.get, dep_uuids)))
            if deps:
                task["description"].add(
                    new_tree(deps, guide_style="b red", hide_root=True)
                )

        yield border_panel(
            flexitable(list(map(keep_headers, tasks))),
            title=wrap(group, "b"),
            style=predictably_random_color(group),
        )


def load_data() -> Any:
    if sys.stdin.isatty():
        return None

    text = sys.stdin.read()
    try:
        data = json.loads(text)
        assert data
    except json.JSONDecodeError:
        console.print(format_string(text))
        sys.exit(0)
        # msg = "Broken JSON"
    except AssertionError:
        sys.exit(0)
    else:
        return data
    console.log(wrap(msg, "b red"), log_locals=True)
    sys.exit(1)


@singledispatch
def draw_data(data: Union[JSONDict, List[JSONDict]]) -> Any:
    return None


def get_args() -> JSONDict:
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("args", nargs="*", default=[])
    return vars(parser.parse_args())


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict) -> Iterator[ConsoleRenderable]:
    if "values" in data and "title" in data:
        values, title = data.pop("values", None), data.pop("title", None)
        calls: Dict[str, Callable[List[JSONDict], Iterator[ConsoleRenderable]]] = {
            "Pull Requests": pulls_table,
            "Hue lights": lights_table,
            "Calendar": calendar_table,
            "Album": albums_table,
            "Tasks": tasks_table,
        }
        table_func = calls.get(title)
        if table_func:
            yield from table_func(values, **data, **get_args())
        else:
            yield flexitable(values)
    else:
        yield flexitable(data)


@draw_data.register(list)
def _draw_data_list(data: List[JSONDict]) -> Iterator[ConsoleRenderable]:
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
