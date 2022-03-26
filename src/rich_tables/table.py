import itertools as it
import json
import operator as op
import random
import sys
from collections import OrderedDict
from functools import partial, singledispatch
from os import environ, path
from typing import Any, Callable, Dict, Iterable, List, SupportsFloat, Tuple, Type, Union

from dateutil.parser import parse
from ordered_set import OrderedSet
from rich import box
from rich.align import Align
from rich.bar import Bar
from rich.columns import Columns
from rich.console import Console, ConsoleRenderable, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.text import Text
from rich.theme import Theme

from .music import make_albums_table, make_tracks_table
from .utils import (
    FIELDS_MAP,
    border_panel,
    duration2human,
    format_with_color,
    make_difftext,
    md_panel,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    time2human,
    wrap
)

JSONDict = Dict[str, Any]
GroupsDict = Dict[str, List]


def get_console():
    tpath = path.join(environ.get("XDG_CONFIG_HOME") or "", "rich", "config.ini")
    theme = Theme.from_file(open(tpath))
    return Console(force_terminal=True, force_interactive=True, theme=theme)


console = get_console()
print = console.print


def make_diff_table(group_to_data: GroupsDict) -> None:
    # diff_table = new_table(expand=True)
    # for group_name, item_lists in group_to_data.items():
    #     for items in item_lists:
    #         headers = list(items[0].keys())
    #         for head in ["before", "after"]:
    #             headers.remove(head)
    #         headers.append("diff")
    #         group_title = items[0].get(group_name) or ""
    #         title = "".join(["─" * 5, "  ", wrap(group_title, "b"), "  ", "─" * 5])

    #         table = new_table()
    #         for item in items:
    #             item["diff"] = make_difftext(*op.itemgetter("before", "after")(item))
    #             item.pop(group_name, None)
    #             table.add_row(*map(lambda x: str(x) if x else " ", item.values()))
    #         diff_table.add_row(simple_panel(table, title=title, padding=1))
    group_to_data = dict(hello=group_to_data)
    print(group_to_data)
    diff_table = new_table(expand=True)
    for group_name, item_lists in group_to_data.items():
        for items in item_lists:
            headers = list(items[0].keys())
            for head in ["before", "after"]:
                headers.remove(head)
            headers.append("diff")
            group_title = items[0].get(group_name) or ""
            title = "".join(["─" * 5, "  ", wrap(group_title, "b"), "  ", "─" * 5])

            table = new_table()
            for item in items:
                item["diff"] = make_difftext(*op.itemgetter("before", "after")(item))
                item.pop(group_name, None)
                table.add_row(*map(lambda x: str(x) if x else " ", item.values()))
            diff_table.add_row(simple_panel(table, title=title, padding=1))


# def get_bar(count: SupportsFloat, min_count: SupportsFloat, total_count: SupportsFloat) -> ConsoleRenderable:
def get_bar(count: SupportsFloat, total_count: SupportsFloat) -> Bar:
    ratio = count / total_count if total_count else 0
    random.seed(str(total_count))
    rand = partial(random.randint, 50, 180)

    def norm():
        return round(rand() * ratio)

    color = "#{:0>2X}{:0>2X}{:0>2X}".format(norm(), norm(), norm())
    return Align(Bar(total_count, 0, count, color=color), vertical="middle")
    # return Align(Bar(float(count) or 0, float(min_count) or 0, float(total_count) or 0, color=color), vertical="middle")


def make_counts_table(data: List[JSONDict]) -> Table:
    headers = set(data[0])
    count_col_name, max_col_name = "count", "total"
    if count_col_name not in headers:
        col_map = {int: "count", str: "desc", float: "count"}
        col_name = {col_map[type(v)]: k for k, v in data[0].items()}
        count_col_name = col_name["count"]
    all_values = list(map(float, map(op.methodcaller("get", count_col_name, 0), data)))
    if not any(map(lambda x: 1 > x > 0, all_values)):
        all_values = list(map(int, all_values))
    max_count, total_count = max(all_values), sum(all_values)
    # min_count, max_count, total_count = min(all_values), max(all_values), sum(all_values)

    # if max_col_name in headers:
    #     max_values = list(map(float, map(op.methodcaller("get", max_col_name, 0), data)))
    # else:
    #     max_values = [max(all_values)] * len(all_values)
    other_col_names = list(
        filter(lambda x: x not in {count_col_name, max_col_name}, data[0])
    )

    table = new_table(
        *map(lambda x: Column(x, overflow="fold"), other_col_names),
        count_col_name,
        justify="left",
        caption_justify="left",
    )
    # for item, count_val, max_val in zip(data, all_values, max_values):
    for item, count_val in zip(data, all_values):
        if count_col_name in {"duration", "total_duration"}:
            count_header = duration2human(count_val, 2)
        else:
            count_header = FIELDS_MAP[count_col_name](count_val)
            # count_header = "{:<2}% {}/{}".format(round(count_val/max_val*100), count_val, int(max_val))
        table.add_row(
            *map(
                lambda x: Align(x, vertical="middle"),
                (
                    *map(
                        lambda x: FIELDS_MAP[x](item.get(x) or "") if x in FIELDS_MAP
                        # else Text(item.get(x) or "")
                        # if "[" in item.get(x)
                        else item.get(x),
                        other_col_names,
                    ),
                    count_header,
                    get_bar(count_val, max_count),
                    # get_bar(count_val, min_count, max_count),
                ),
            )
        )
    if count_col_name in {"duration", "total_duration"}:
        total_count = duration2human(sum(all_values), 2)
        table.caption = f"Total {total_count}"
    return table


def make_pulls_table(data: List[JSONDict]) -> None:
    def comment_panel(comment: Dict[str, str], **kwargs: Any) -> Panel:
        return md_panel(
            comment["body"],
            title=" ".join(
                map(lambda x: get_val(comment, x), ["state", "author", "createdAt"])
            ),
            border_style="green" if comment.get("isResolved") else "red",
        )

    def syntax_panel(content: str, lexer: str, **kwargs: Any) -> Panel:
        return Panel(
            Syntax(
                content,
                lexer,
                theme="paraiso-dark",
                background_color="black",
                word_wrap=True,
            ),
            style=kwargs.get("style") or "black",
            width=200,
            title=kwargs.get("title") or "",
        )

    state_map = {
        "APPROVED": "green",
        "MERGED": "magenta",
        "COMMENTED": "yellow",
        "CHANGES_REQUESTED": "yellow",
        "REVIEW_REQUIRED": "red",
        "DISMISSED": "red",
        "OPEN": "green",
        "UNSEEN": "bold black on red",
        "SEEN": "bold black on green",
        "True": "bold green",
        "False": "bold red",
    }
    exclude = {
        "title",
        "body",
        "reviews",
        "comments",
        "reviewThreads",
        "url",
    }
    pr = data[0]
    FIELDS_MAP.update(
        {
            "author": format_with_color,
            "participants": lambda x: "  ".join(map(format_with_color, x)),
            "state": lambda x: wrap(wrap(x, "b"), state_map.get(x, "default")),
            "isReadByViewer": lambda x: wrap(str(x), state_map.get(str(x), "default")),
            "updatedAt": lambda x: time2human(x, pad=False, use_colors=True),
            "createdAt": lambda x: time2human(x, pad=False, use_colors=True),
            "repository": lambda x: x.get("name"),
            "files": lambda files: "\n".join(
                map(
                    lambda f: wrap(
                        (f"+{f['additions']}" if f["additions"] else "").rjust(5),
                        "b green",
                    )
                    + " "
                    + wrap(
                        (f"-{f['deletions']}" if f["deletions"] else "").rjust(3),
                        "b red",
                    )
                    + " "
                    + wrap(f["path"], "b"),
                    files,
                )
            ),
        }
    )

    keys = sorted(set(pr) - exclude)
    info_table = new_table(rows=map(lambda x: (wrap(x, "b"), get_val(pr, x)), keys))

    reviews = []
    for review in pr.get("reviews") or []:
        if review["body"]:
            reviews.append(comment_panel(review))

    files = []
    rthreads = pr.get("reviewThreads") or []
    for file, threads in it.groupby(rthreads, op.itemgetter("path")):
        rows: List[ConsoleRenderable] = []
        for thread in threads:
            rows.append(syntax_panel(thread["comments"][0].get("diffHunk") or "", "diff"))
            for comment in thread.get("comments") or []:
                rows.append(comment_panel(comment))
        files.append(border_panel(Group(*rows), title=wrap(thread["path"], "b magenta")))

    info_section = [simple_panel(info_table), md_panel(pr["body"], box=box.SIMPLE)]
    gr = Group(
        "",
        Rule(wrap(pr.get("title", " "), "b")),
        new_table(rows=[info_section]),
        *reviews,
        *files,
    )
    print(gr)


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
def make_generic_table(
    data: Union[JSONDict, List, ConsoleRenderable, str], header: str = ""
) -> Any:
    return str(data)


@make_generic_table.register(str)
def _str(data: Union[str, int], header: str = "") -> Any:
    return FIELDS_MAP[header](data)


@make_generic_table.register
def _renderable(data: ConsoleRenderable) -> ConsoleRenderable:
    return data


@make_generic_table.register(dict)
def _dict(data: JSONDict):
    table = new_table()
    for key, content in data.items():
        if isinstance(content, str):
            content = make_generic_table(content, key)
        else:
            content = make_generic_table(content)
        add_to_table(table, content, key)

    if table.columns:
        table.columns[0].style = "bold misty_rose1"
    return border_panel(table)


@make_generic_table.register(list)
def _list(data: List[JSONDict]):
    def only(data_list: Iterable[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    table = new_table()
    if only(data, str):
        # ["hello", "hi", "bye", ...]
        return Columns(list(map(format_with_color, data)), equal=True)

    elif only(data, dict) and len(set(map(str, map(dict.keys, data)))) == 1:
        # [{"hello": 1, "hi": true}, {"hello": 100, "hi": true}]
        if not table.rows:
            table = new_table(*data[0].keys())
        vals_types = set(map(type, data[0].values()))
        if (
            len(data[0]) == 2
            and len(vals_types.intersection({int, float, str})) == 2
            or "count" in set(data[0].keys())
        ):
            # [{"some_count": 10, "some_entity": "entity"}, ...]
            table = make_counts_table(data)
        else:
            for item in data:
                row = []
                for key, value in item.items():
                    if isinstance(value, str):
                        row.append(make_generic_table(value, key))
                    else:
                        row.append(make_generic_table(value))
                table.add_row(*row)

    else:
        # [{}, "bye", True]
        for item in data:
            add_to_table(table, make_generic_table(item))

    return simple_panel(table)


def make_lights_table(lights: List[JSONDict]) -> Table:
    from rgbxy import Converter

    headers = lights[0].keys()
    table = new_table(*headers)
    conv = Converter()
    for light in lights:
        xy = light.get("xy")
        if xy:
            color = conv.xy_to_hex(*xy)
            light["xy"] = wrap("   a", f"#{color} on #{color}")
        table.add_row(
            *map(str, map(light.get, headers)), style="" if light["on"] else "dim"
        )
    return table


def make_calendar_table(events: List[JSONDict]) -> None:
    def get_start_end(start: str, end: str) -> Tuple[int, int]:
        if start == end == "00:00":
            return 0, 86400
        day_start_ts = parse("00:00").timestamp()
        return int(parse(start).timestamp() - day_start_ts), int(
            parse(end).timestamp() - day_start_ts
        )

    calendars = set(map(op.itemgetter("calendar"), events))
    cal_to_color = dict(zip(calendars, map(predictably_random_color, calendars)))
    cal_fmted = it.starmap(
        lambda x, y: wrap(f" {x} ", f"b black on {y}"), cal_to_color.items()
    )
    print(Columns(cal_fmted, expand=True, equal=True, align="center"))

    updated_events = []
    for event in events:
        color = cal_to_color[event["calendar"]]
        event["summary"] = wrap(event["summary"], f"b {color}")
        event["bar"] = Bar(
            86400, *get_start_end(event["start_time"], event["end_time"]), color=color
        )
        updated_events.append(event)

    table = new_table(expand=True)
    keys = "summary", "start_time", "end_time", "bar"  # , "location"
    for date, day_events in it.groupby(updated_events, op.itemgetter("start_date")):
        table.add_row()
        table.add_row(wrap(f"   {date}   ", "on grey3"))
        for event in day_events:
            table.add_row(*op.itemgetter(*keys)(event))
    print(table)


def get_val(obj: JSONDict, field: str) -> str:
    return FIELDS_MAP[field](obj[field]) if obj.get(field) else ""


def make_tasks_table(tasks: List[JSONDict]) -> None:
    get_time = partial(time2human, use_colors=True, pad=False)
    fields_map = dict(
        id=str,
        urgency=lambda x: str(round(x, 1)),
        description=lambda x: x,
        due=get_time,
        end=get_time,
        sched=get_time,
        tags=lambda x: " ".join(map(format_with_color, x or [])),
        project=format_with_color,
        modified=get_time,
        annotations=lambda l: "\n".join(
            map(
                lambda x: wrap(time2human(x["entry"], pad=False), "b")
                + ": "
                + wrap(x["description"], "i"),
                reversed(l),
            )
        ),
    )
    FIELDS_MAP.update(fields_map)
    status_map = {
        "completed": "b s black on green",
        "deleted": "s red",
        "pending": "white",
        "started": "b green",
        "recurring": "i magenta",
    }
    id_to_desc = uuid_to_id = {}
    for task in tasks:
        task["sched"] = task.get("scheduled")
        if not task.get("id"):
            task["id"] = task["uuid"].split("-")[0]
        uuid_to_id[task["uuid"]] = task["id"]

        if task.get("start"):
            task["status"] = "started"

        recur = task.get("recur")
        if recur:
            if task.get("status") == "recurring":
                continue
            else:
                task["status"] = "recurring"
                task["description"] += f" ({recur})"
        desc = wrap(task["description"], status_map[task["status"]])
        if task.get("priority") == "H":
            desc = f"[b]([red]![/])[/] {desc}"
        id_to_desc[task["id"]] = desc

    group_by = tasks[0].get("group_by") or ""
    headers = OrderedSet(["urgency", "id", *fields_map.keys()]) - {group_by}

    for group, task_group in it.groupby(
        sorted(
            tasks,
            key=lambda x: (x.get(group_by) or "", x.get("urgency") or 0),
            reverse=True,
        ),
        lambda x: x.get(group_by) or f"no [b]{group_by}[/]",
    ):
        project_color = predictably_random_color(str(group))
        table = new_table(padding=(0, 1, 0, 1))
        for task in task_group:
            task_obj = id_to_desc.get(task["id"])
            if not task_obj:
                continue

            task_tree = new_tree(title=task_obj, guide_style=project_color)
            ann = task.pop("annotations", None)
            if ann:
                task_tree.add(FIELDS_MAP["annotations"](ann))
            for kuid in task.get("depends") or []:
                dep = id_to_desc.get(uuid_to_id.get(kuid))
                if dep:
                    task_tree.add(wrap(str(uuid_to_id[kuid]), "b") + " " + dep)
            task["description"] = task_tree
            table.add_row(*map(lambda x: get_val(task, x), headers))

        for col in table.columns.copy():
            try:
                next(filter(op.truth, col.cells))
            except StopIteration:
                table.columns.remove(col)
        panel = simple_panel if group == "started" else border_panel
        print(panel(table, title=wrap(group, "b"), style=project_color))


def load_data() -> Any:
    d = sys.stdin.read()
    try:
        data = json.loads(d)
        assert data and (data.get("values") if "values" in data else True)
    except (json.JSONDecodeError, AssertionError):
        console.print(wrap("No data", "b red"))
        exit(1)
    else:
        return data


@singledispatch
def draw_data(data: Union[JSONDict, List], title: str = "") -> None:
    console.print(data)


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict) -> None:
    if "values" in data:
        return draw_data(data["values"], data.get("title") or "")
    console.print(make_generic_table(data))


@draw_data.register(list)
def _draw_data_list(data: List[JSONDict], title: str = "") -> None:
    calls: Dict[str, Callable] = {
        "Pull Requests": make_pulls_table,
        "JIRA Diff": make_diff_table,
        "Hue lights": make_lights_table,
        "Calendar": make_calendar_table,
        "Album": make_albums_table,
        "Music": make_tracks_table,
        "Count": make_counts_table,
        "Tasks": make_tasks_table,
        "": make_generic_table,
    }
    try:
        func = calls[title]
    except KeyError:
        print(title.encode())
        ret = draw_data(data[0]) if len(data) == 1 else make_generic_table(data)
    else:
        ret = func(data)

    if ret:
        console.print(ret)


def main():
    args = set()
    if len(sys.argv) > 1:
        args.update(sys.argv[1:])

    data = load_data()
    if "-j" in args:
        console.print_json(data=data)
    else:
        try:
            draw_data(data)
        except Exception as exc:
            console.print_json(data=data)
            console.print_exception(extra_lines=4, show_locals=True)
            raise exc


if __name__ == "__main__":
    main()
