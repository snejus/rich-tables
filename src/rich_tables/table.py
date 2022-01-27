import itertools as it
import json
import operator as op
import re
import sys
from datetime import datetime
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Type, Union

from rich import box, print
from rich.bar import Bar
from rich.columns import Columns
from rich.console import Console, ConsoleRenderable, RenderableType
from rich.table import Table

from .music import make_albums_table, make_tracks_table
from .utils import (
    border_panel,
    colored_split,
    comment_panel,
    duration2human,
    format_with_color,
    make_difftext,
    md_panel,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    syntax_panel,
    time2human,
    wrap,
)

console = Console(force_terminal=True, force_interactive=True)
JSONDict = Dict[str, Any]
GroupsDict = Dict[str, List]


def make_diff_table(group_to_data: GroupsDict) -> None:
    diff_table = new_table(expand=True)
    for group_name, item_lists in group_to_data.items():
        for items in item_lists:
            headers = list(items[0].keys())
            for head in ["before", "after"]:
                headers.remove(head)
            headers.append("diff")
            group_title = items[0].get(group_name) or ""
            title = "─" * 5 + "  " + wrap(group_title, "b") + "  " + "─" * 5

            table = new_table()
            for item in items:
                item["diff"] = make_difftext(*op.itemgetter("before", "after")(item))
                item.pop(group_name, None)
                table.add_row(*map(lambda x: str(x) if x else " ", item.values()))
            diff_table.add_row(simple_panel(table, title=title, padding=1))


def make_counts_table(data: List[JSONDict]) -> None:
    total_count = sum(map(op.methodcaller("get", "count", 0), data))

    table = new_table()

    def add_bar(count: int, *args) -> None:
        rand1 = rand2 = rand3 = round(255 * float(count / total_count))
        color = "#{:0>2X}{:0>2X}{:0>2X}".format(rand1, rand2, rand3)
        bar = Bar(total_count, 0, count, color=color)
        table.add_row(*args, str(count), bar)

    keys = set(data[0].keys()) - {"count"}
    for item in data:
        count = item["count"]
        desc = op.itemgetter(*keys)(item)
        add_bar(count, *desc)
    add_bar(total_count, "", "total")


def make_time_table(data: List[JSONDict]) -> Table:
    group_by = set(data[0].keys()).difference({"duration"}).pop()
    total_time = sum(map(op.methodcaller("get", "duration", 0), data))

    table = new_table()

    def add_duration_bar(duration: int, categories: str) -> None:
        color = predictably_random_color(categories)
        catstr = categories
        if categories == "total":
            catstr = wrap(catstr, "dim")
        bar = Bar(total_time, 0, duration, color=color)
        table.add_row(catstr, duration2human(duration), bar)

    data.append({group_by: "total", "duration": total_time})
    for duration, categories in map(op.itemgetter("duration", group_by), data):
        add_duration_bar(duration, categories)

    return table


def make_pulls_table(data: List[JSONDict]) -> None:
    state_map = {
        "APPROVED": "green",
        "MERGED": "magenta",
        "COMMENTED": "yellow",
        "CHANGES_REQUESTED": "yellow",
        "REVIEW_REQUIRED": "red",
        "DISMISSED": "red",
        "OPEN": "green",
        " UNSEEN ": "bold black on red",
        " SEEN ": "bold black on green",
    }
    exclude = {
        "title",
        "body",
        "reviews",
        "comments",
        "reviewThreads",
        "files",
        "participants",
    }

    table = new_table()
    for pr in data:
        desc_table = new_table(expand=True)
        title = wrap(pr.get("title", ""), "b")
        listvals: List[str] = []
        for key, val in pr.items():
            if isinstance(key, str) and key not in exclude:
                val = str(val)
                if "[" not in val:
                    color = state_map.get(val, val)
                    if color:
                        val = wrap(val, f"b {color}")
                listvals.append("{:<28}{}".format(wrap(key, "b"), val))
        tree = new_tree(listvals, title=title)
        tree.add(
            "{:<28}{}".format(
                wrap("participants", "b"),
                "\t".join(map(format_with_color, pr["participants"])),
            )
        )

        tree.add("")
        for file in pr["files"]:
            tree.add("{:<30}{:<26}{}".format(*file))
        desc_table.add_row(simple_panel(tree), md_panel(pr["body"], box=box.SIMPLE))
        table.add_row(simple_panel(desc_table))

        reviews_table = new_table()
        reviews = pr.get("reviews") or []
        for review in reviews:
            state = review["state"]
            if state == "COMMENTED":
                continue
            color = state_map.get(state, "default")
            review["state"] = wrap(state, f"b {color}")
            review["body"] = re.sub(r"(^|\n)", "\\1> ", review["body"])
            reviews_table.add_row(comment_panel(review))
        if len(reviews):
            table.add_row(
                simple_panel(
                    reviews_table, title=wrap("Reviews", "b"), title_align="left"
                )
            )

        for thread in pr.get("reviewThreads") or []:
            thread_table = new_table()
            diff_panel = None
            comments_table = new_table()
            comments = thread.get("comments")
            for comment in comments:
                if not diff_panel and "diffHunk" in comment:
                    diff_panel = syntax_panel(
                        re.sub(r"[\[\]\\]", "", comment["diffHunk"]),
                        "diff",
                        box=box.ROUNDED,
                    )
                comments_table.add_row(comment_panel(comment))

            parts: Iterable[RenderableType] = filter(
                op.truth, [diff_panel or "", comments_table]
            )
            thread_table.add_row(*map(simple_panel, parts))

            file_line = thread.get("line")
            title = thread.get("path") + " " + wrap(file_line, "b") if file_line else ""
            style = "green" if thread.get("isResolved") else "red"
            table.add_row(border_panel(thread_table, title=title, border_style=style))

        comments = pr.get("comments") or []
        if len(comments):
            table.add_row(wrap("Comments", "b"))
            for comment in comments:
                table.add_row(comment_panel(comment))
        print(table)


def add_to_table(table: Table, content: Any, key: str = ""):
    args = []
    if key:
        args.append(key)
    if isinstance(content, list):
        args.extend(content)
    else:
        args.append(content)
    table.add_row(*args)


@singledispatch
def make_generic_table(data: Union[JSONDict, List]) -> Any:
    if not data:
        return ""
    return str(data)


@make_generic_table.register
def _dict(data: dict):
    table = new_table()
    for key, content in data.items():
        if key in {"genre", "style"}:
            content = colored_split(content)
            content.align = "left"
        else:
            content = make_generic_table(content)
        add_to_table(table, content, key=str(key))

    table.columns[0].style = "bold misty_rose1"
    return border_panel(table)


@make_generic_table.register
def _list(data: list):
    def only(data_list: Iterable[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    table = new_table()
    if only(data, str):
        # ["hello", "hi", "bye", ...]
        return Columns(list(map(lambda x: wrap(x, "b"), data)), equal=True)

    if only(data, dict) and len(set(map(str, map(dict.keys, data)))) == 1:
        # [{"hello": 1, "hi": true}, {"hello": 100, "hi": true}]
        if not table.rows:
            keys = list(data[0].keys())
            table = new_table(*keys)
        for item in data:
            row = []
            for value in item.values():
                row.append(make_generic_table(value))
            table.add_row(*row)
    else:
        # [{}, "bye", True]
        for item in data:
            add_to_table(table, make_generic_table(item))

    return simple_panel(table)


@make_generic_table.register
def _renderable(data: ConsoleRenderable) -> ConsoleRenderable:
    return data


def make_lights_table(lights: List[JSONDict]) -> None:
    from rgbxy import Converter

    table = new_table(*lights[0].keys())
    conv = Converter()
    for light in lights:
        color = conv.xy_to_hex(*light.get("xy") or [0, 0])
        light["xy"] = wrap("   a", f"#{color} on #{color}")
        table.add_row(*map(lambda x: str(x) if x else " ", light.values()))
    table.columns[1].justify = "left"

    console.print(simple_panel(table))


def make_calendar_table(events: List[JSONDict]) -> None:
    color_header = "calendar_color"
    updated_events = []
    keys = "start_time", "end_time", "start_date", "summary", "location"
    getitems = op.itemgetter(*keys)
    for event in events:
        style = event[color_header]
        event.pop(color_header)
        updated_event = dict(cal=wrap("aaa", f"{style} on {style}"))
        updated_event.update(**dict(zip(keys, getitems(event))))
        updated_events.append(updated_event)

    for date, day_events in it.groupby(updated_events, op.itemgetter("start_date")):
        table = new_table()
        for event in day_events:
            table.add_row(*event.values())
        print(simple_panel(table, title=wrap(date, "b"), style="cyan"))


def get_val(fields_map: Dict[str, Callable], obj: JSONDict, field: str) -> str:
    return fields_map[field](obj[field]) if obj.get(field) else ""


def make_tasks_table(task_groups: GroupsDict) -> None:
    fields_map: Dict[str, Callable] = OrderedDict(
        id=lambda x: str(x),
        urgency=lambda x: str(round(x, 1)),
        description=lambda x: x,
        due=lambda x: re.sub(
            r"(.*) ago$",
            wrap("\\1", "b red"),
            re.sub(
                r"^in (.*)",
                wrap("\\1", "b green"),
                time2human(int(parse(x).timestamp())),
            ),
        ),
        tags=lambda x: " ".join(map(format_with_color, x or [])),
        # modified=lambda x: time2human(int(parse(x).timestamp())),
        # mask=lambda x: x,
        # imask=lambda x: str(x),
    )
    headers = fields_map.keys()
    status_map = {
        "completed": "s green",
        "deleted": "s red",
        "pending": "white",
        "started": "b green",
        "recurring": "i magenta",
    }
    index = {}
    for task in it.chain(*it.starmap(lambda x, y: y, task_groups.items())):
        if task.get("start"):
            task["status"] = "started"

        recur = task.get("recur")
        if recur and task.get("status") == "recurring":
            task["description"] += f" ({recur})"
        index[task["uuid"]] = wrap(task["description"], status_map[task["status"]])

    get_value = partial(get_val, fields_map)
    for group, tasks in task_groups.items():
        table = new_table()
        for task in tasks:
            task_tree = new_tree(title=index[task["uuid"]])
            for uuid in task.get("depends") or []:
                dep = index.get(uuid)
                if dep:
                    task_tree.add(dep)
            task["description"] = task_tree
            table.add_row(*map(partial(get_value, task), headers))
        print(
            border_panel(
                table,
                title=wrap(f"  {group}  ", "b on #000000"),
                style=predictably_random_color(group),
            )
        )


def load_data() -> Any:
    data = None
    d = sys.stdin.read()
    try:
        data = json.loads(d)
        assert data
    except (json.JSONDecodeError, AssertionError):
        console.print(wrap("No data", "b red"))
        exit(1)
    else:
        return data


def draw_data(title, data, groups={}):
    # type: (str, Union[List, Dict], GroupsDict) -> None
    if groups:
        console.print(make_generic_table(data))
    elif isinstance(data, dict):
        if title == "Tasks":
            make_tasks_table(data)
        else:
            console.print(make_generic_table(data))
    elif isinstance(data, list):
        if title == "Pull Requests":
            make_pulls_table(data)
        elif title == "JIRA Diff":
            make_diff_table(groups)
        elif title == "Time Usage Report":
            print(make_time_table(data))
        elif " count" in title.casefold():
            make_counts_table(data)
        elif title == "Hue lights":
            make_lights_table(data)
        elif title == "Calendar":
            make_calendar_table(data)
        elif title == "Album":
            make_albums_table(data)
        elif title == "Music":
            make_tracks_table(data)
        else:
            console.print(make_generic_table(data))


def main():
    args = set()
    if len(sys.argv) > 1:
        args.update(sys.argv[1:])

    data = load_data()
    if "-j" in args:
        console.print_json(data=data)
    else:
        groups: GroupsDict = {}
        values = data
        data_title = ""
        if isinstance(data, dict):
            data_title = data.get("title") or data_title
            values = data.get("values") or values
            groups = data.get("groups") or groups

        try:
            draw_data(data_title, values, groups=groups)
        except Exception as exc:
            console.print_json(data=data)
            console.print_exception(extra_lines=4, show_locals=True)
            raise exc


if __name__ == "__main__":
    main()
