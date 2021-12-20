#!/media/poetry/virtualenvs/snejus-scripts-pRoBlG0N-py3.8/bin/python

import itertools as it
import json
import operator as op
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Type, Union

from music import make_albums_table, make_music_table, make_release_table
from rich import box, print
from rich.bar import Bar
from rich.console import Console, ConsoleRenderable
from rich.highlighter import RegexHighlighter
from rich.panel import Panel
from utils import (
    border_panel,
    colored_split,
    comment_panel,
    format_with_color,
    md_panel,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    syntax_panel,
    time2human,
    timeint2human,
    wrap,
)

JSONDict = Dict[str, Any]
GroupsDict = Dict[str, List]


def fmtdiff(change: str, before: str, after: str) -> str:
    retval = before
    if change == "insert":
        retval = wrap(after, "b green")
    elif change == "delete":
        retval = wrap(before, "b strike red")
    elif change == "replace":
        retval = wrap(before, "b strike red") + wrap(after, "b green")
    return retval


def make_difftext(before: str, after: str) -> str:
    def preparse(value: str) -> str:
        return value.strip().replace("[]", "~")

    before = preparse(before)
    after = preparse(after)

    matcher = SequenceMatcher(isjunk=lambda x: x in r"\n ", a=before, b=after)
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    return diff


def make_diff_table(group_to_data: GroupsDict) -> None:
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
            root.add_row(simple_panel(table, title=title, padding=1))
        root.expand = True


def make_counts_table(data: List[JSONDict]) -> None:
    total_count = sum(map(op.methodcaller("get", "count", 0), data))

    def add_bar(count: int, *args) -> None:
        rand1 = rand2 = rand3 = round(255 * float(count / total_count))
        color = "#{:0>2X}{:0>2X}{:0>2X}".format(rand1, rand2, rand3)
        bar = Bar(total_count, 0, count, color=color)
        root.add_row(*args, str(count), bar)

    keys = set(data[0].keys()) - {"count"}
    for item in data:
        count = item["count"]
        desc = op.itemgetter(*keys)(item)
        add_bar(count, *desc)
    add_bar(total_count, "", "total")


def make_time_table(data: List[JSONDict]) -> None:
    group_by = set(data[0].keys()).difference({"duration"}).pop()
    total_time = sum(map(op.methodcaller("get", "duration", 0), data))

    def add_duration_bar(duration: int, categories: str) -> None:
        color = predictably_random_color(
            categories
        )  # , ratio=float(duration / total_time))
        catstr = "{:<27}{}".format(categories, timeint2human(duration))
        if categories == "total":
            catstr = wrap(catstr, "dim")
        bar = Bar(total_time, 0, duration, color=color)
        root.add_row(catstr, bar)

    data.append({group_by: "total", "duration": total_time})
    for duration, categories in map(op.itemgetter("duration", group_by), data):
        add_duration_bar(duration, categories)


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
    for pr in data:
        table = new_table(expand=True)
        exclude = {
            "title",
            "body",
            "reviews",
            "comments",
            "reviewThreads",
            "files",
            "participants",
        }
        title = wrap(pr.get("title", ""), "b")
        listvals: List[str] = []
        for key, val in pr.items():
            if isinstance(key, str) and key not in exclude:
                if "[" not in str(val):
                    val = str(val)
                    color = state_map.get(val, val)
                    if color:
                        val = wrap(val, "bold {color}")
                listvals.append("{:<28}{}".format(wrap(key, "b"), val))
        tree = new_tree(listvals, title=title)
        tree.add(
            "{:<28}{}".format(
                "[b]participants[/b]",
                "\t".join(map(format_with_color, pr["participants"])),
            )
        )

        tree.add("")
        for file in pr["files"]:
            tree.add("{:<30}{:<26}{}".format(*file))
        table.add_row(simple_panel(tree), md_panel(pr["body"], box=box.SIMPLE))
        root.add_row(simple_panel(table))
        table = new_table()

        reviews = pr.get("reviews") or []
        for review in reviews:
            state = review["state"]
            if state == "COMMENTED":
                continue
            color = state_map.get(state, "default")
            review["state"] = f"[b {color}]{state}[/b {color}]"
            review["body"] = re.sub(r"(^|\n)", "\\1> ", review["body"])
            table.add_row(comment_panel(review))
        if len(reviews):
            root.add_row(simple_panel(table, title="[b]Reviews[/b]", title_align="left"))

        for thread in pr.get("reviewThreads") or []:
            thread_table = new_table()
            diff_panel = None  # type: Panel
            comments_table = new_table()
            for comment in thread.get("comments") or []:
                if not diff_panel and "diffHunk" in comment:
                    diff_panel = syntax_panel(
                        re.sub(r"[\[\]\\]", "", comment["diffHunk"]), "diff"
                    )
                    diff_panel.box = box.ROUNDED
                comments_table.add_row(comment_panel(comment))

            thread_table.add_row(simple_panel(diff_panel), simple_panel(comments_table))
            file_line = thread.get("line")
            title = thread.get("path") + " " + wrap(file_line, "b") if file_line else ""
            style = "green" if thread.get("isResolved") else "red"
            root.add_row(border_panel(thread_table, title=title, border_style=style))

        comments = pr.get("comments") or []
        if len(comments):
            root.add_row("[b]Comments[/b]")
            for comment in comments:
                root.add_row(comment_panel(comment))


def prepare_any_data(data: Union[JSONDict, List], ret: bool = False) -> Any:
    table = new_table()

    def only(data_list: List[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    def simple_vals(data_list: List[Any]) -> bool:
        return not any(map(lambda x: isinstance(x, (dict, list)), data_list))

    if not data:
        return ""
    if isinstance(data, list):
        if only(data, dict):
            keys = list(data[0].keys())
            if not table.rows:
                table = new_table(*keys)
            for mapping in data:
                table.add_row(*prepare_any_data(list(mapping.values())))
            return border_panel(table)
        else:
            mapped = []
            for item in data:
                prepped = prepare_any_data(item)
                mapped.append(prepped)
            return mapped

    elif isinstance(data, dict):
        for key, content in data.items():
            if key in {"genre", "style"}:
                content = colored_split(content)
                content.align = "left"
            else:
                content = prepare_any_data(content)
            table.add_row(str(key), content)

        table.columns[0].style = "bold misty_rose1"
        return border_panel(table)
    elif isinstance(data, ConsoleRenderable):
        return data
    else:
        return str(data)


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


def make_tasks_table(task_groups: GroupsDict) -> None:
    index = {}
    for group, tasks in task_groups.items():
        for task in tasks:
            task["tags"] = " ~ ".join(task.get("tags") or [])
            status = task["status"]
            if status == "completed":
                task["description"] = wrap(task["description"], "s green")
            elif status == "deleted":
                task["description"] = wrap(task["description"], "s red")
            for key in ("entry", "modified", "end"):
                val = task.get(key)
                if val:
                    date_time = datetime.strptime(val, "%Y%m%dT%H%M%SZ")
                    task[key] = time2human(int(date_time.timestamp()))
            task["title"] = f"{(task['id'] or ''):<3} {task['description']}"
            index[task["uuid"]] = new_tree(title=task["title"])

    for group, tasks in task_groups.items():
        color = predictably_random_color(group)
        tree = new_tree(guide_style=color, highlight=True)
        for task in tasks:
            task_tree = index[task["uuid"]]
            for uuid in task.get("depends") or []:
                dep = None
                dep = index.get(uuid)
                if dep:
                    task_tree.add(dep)
            tree.add(task_tree)
        console.print(border_panel(tree, title=group, border_style=color))


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
        console.print(prepare_any_data(data))
    elif isinstance(data, dict):
        if data_title == "Release":
            console.print(Panel(make_release_table(data, ret=True)))
        elif data_title == "Tasks":
            make_tasks_table(data)
        else:
            console.print(prepare_any_data(data))
    elif isinstance(data, list):
        if data_title == "Pull Requests":
            make_pulls_table(data)
        elif data_title == "JIRA Diff":
            make_diff_table(groups)
        elif data_title == "Time Usage Report":
            make_time_table(data)
        elif " count" in data_title.casefold():
            make_counts_table(data)
        elif data_title == "Hue lights":
            make_lights_table(data)
        elif data_title == "Calendar":
            make_calendar_table(data)
        elif data_title == "Album":
            make_albums_table(data)
        elif "music" in data_title.casefold():
            make_music_table(data)
        else:
            console.print(prepare_any_data(data))
        console.print(root)
    # print(prepare_any_data(data))


if __name__ == "__main__":
    console = Console(force_terminal=True, force_interactive=True)
    root = new_table(style="light_steel_blue1")

    data = load_data()
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
        console.print_exception(extra_lines=8, show_locals=True)
        raise exc
