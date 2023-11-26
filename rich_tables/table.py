import itertools as it
import json
import sys
from collections import OrderedDict
from contextlib import suppress
from datetime import datetime, timedelta
from functools import singledispatch
from traceback import format_exc, format_tb
from typing import Any, Callable, Dict, Iterable, Iterator, List, Tuple, Union

from multimethod import DispatchError
from rich.bar import Bar
from rich.columns import Columns
from rich.console import ConsoleRenderable
from rich.panel import Panel
from rich.table import Table
from rich.traceback import install

from .fields import FIELDS_MAP, get_val
from .generic import flexitable
from .github import pulls_table
from .music import albums_table
from .utils import (
    border_panel,
    format_with_color,
    make_console,
    new_table,
    new_tree,
    predictably_random_color,
    time2human,
    wrap,
)

JSONDict = Dict[str, Any]


console = make_console()
install(console=console, show_locals=True)
print = console.print


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
        table.add_row(*map(str, (light.get(x, "") for x in headers)), style=style)
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
            new_events.append(
                {
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
                    "desc": (
                        border_panel(get_val(event, "desc")) if event["desc"] else ""
                    ),
                    "bar": Bar(86400, *get_start_end(start, end), color=color),
                    "summary": event["summary"] or "",
                }
            )

    keys = "name", "start_time", "end_time", "bar"
    month_events: Iterable[JSONDict]
    for year_and_month, month_events in it.groupby(
        new_events, lambda x: x["start"].strftime("%Y %B")
    ):
        table = new_table(*keys, highlight=False, padding=0, show_header=False)
        for day, day_events in it.groupby(
            sorted(month_events, key=lambda x: x.get("start_day") or ""),
            lambda x: x.get("start_day") or "",
        ):
            table.add_row(wrap(day, "b i"))
            for event in day_events:
                if "Week " in event["summary"]:
                    table.add_row("")
                    table.add_dict_item(event, style=event["color"] + " on grey7")
                else:
                    table.add_dict_item(event)
                    # if event["desc"]:
                    #     table.add_row("", "", "", event["desc"])
            table.add_row("")
        yield border_panel(table, title=year_and_month)


def tasktime(datestr: str) -> str:
    return time2human(datetime.strptime(datestr, "%Y%m%dT%H%M%SZ").timestamp())


def tasks_table(tasks: Dict[str, List[JSONDict]]) -> Iterator[Panel]:
    if not tasks:
        return
    fields_map: JSONDict = {
        "id": str,
        "urgency": lambda x: str(round(x, 1)),
        "description": lambda x: x,
        "due": tasktime,
        "end": tasktime,
        "sched": tasktime,
        "tags": lambda x: " ".join(map(format_with_color, x or [])),
        "project": format_with_color,
        "modified": tasktime,
        "annotations": lambda ann: "\n".join(
            wrap(tasktime(a["entry"]), "b") + ": " + wrap(a["description"], "i")
            for a in ann
        ),
    }
    FIELDS_MAP.update(fields_map)
    status_map = {
        "completed": "b s black on green",
        "deleted": "s red",
        "pending": "white",
        "started": "b green",
        "recurring": "i magenta",
    }
    uuid_to_desc = {}
    all_tasks = list(it.chain.from_iterable(tasks.values()))
    for task in (r for r in all_tasks if r.get("recur") and r["status"] != "recurring"):
        task["status"] = "recurring"
        task["description"] += f" ({task})"

    for task in all_tasks:
        task["sched"] = task.get("scheduled")
        if task.get("start"):
            task["status"] = "started"

        desc = wrap(task["description"], status_map[task["status"]])
        if task.get("priority") == "H":
            desc = f"[b]([red]![/])[/] {desc}"

        uuid_to_desc[task["uuid"]] = desc

    headers = ["urgency", "id", *(fields_map.keys() - {"id", "urgency"})]
    headers = [h for h in headers if any(t.get(h) for t in all_tasks)]

    for group_name, task_list in tasks.items():
        table = new_table(padding=(0, 1, 0, 1))
        for task in task_list:
            task_tree = new_tree(title=uuid_to_desc[task["uuid"]], guide_style="white")

            ann = task.pop("annotations", None)
            if ann:
                task_tree.add(FIELDS_MAP["annotations"](ann))
            dep_uuids = task.get("depends") or []
            for dep_line in (
                f"[b]{u}[/b] {uuid_to_desc[u]}"
                for u in set(dep_uuids) & uuid_to_desc.keys()
            ):
                task_tree.add(dep_line, guide_style="red")
            task["description"] = task_tree
            table.add_row(*(get_val(task, h) for h in headers))

        yield border_panel(
            table,
            title=group_name,
            style=(
                "b green"
                if group_name == "started"
                else predictably_random_color(str(group_name))
            ),
        )


def load_data() -> Any:
    text = sys.stdin.read().replace(r"\x00", "")
    try:
        data = json.loads(text or "{}", object_hook=OrderedDict)
        assert data
    except json.JSONDecodeError:
        msg = "Broken JSON"
    except AssertionError:
        exit(0)
    else:
        return data
    console.log(wrap(msg, "b red"), log_locals=True)
    exit(1)


@singledispatch
def draw_data(data: Union[JSONDict, List[JSONDict]]) -> Any:
    return None


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
        if title in calls:
            yield from calls[title](values, **data)
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

        print(FIELDS_MAP["diff"](arguments), highlight=False)
    else:
        if "-s" in set(args):
            console.record = True

        data = load_data()
        if "-j" in args:
            console.print_json(data=data)
        else:
            try:
                for ret in draw_data(data):
                    console.print(ret)
            except DispatchError as e:
                if e.__cause__:
                    raise e.__cause__ from None
                raise

        if "-s" in set(args):
            console.save_html("saved.html")


if __name__ == "__main__":
    main()
