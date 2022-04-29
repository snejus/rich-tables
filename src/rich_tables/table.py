import itertools as it
import json
import operator as op
import sys
from datetime import datetime, timedelta
from functools import partial, singledispatch
from typing import Any, Callable, Dict, Iterable, List, Tuple, Union

from dateutil.parser import parse
from ordered_set import OrderedSet
from rich.bar import Bar
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table

from .generic import flexitable
from .music import albums_table, tracks_table
from .utils import (
    FIELDS_MAP,
    border_panel,
    format_with_color,
    get_val,
    make_console,
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


console = make_console()
print = console.print


def pulls_table(data: List[JSONDict]) -> Iterable[Union[str, ConsoleRenderable]]:
    def comment_panel(comment: Dict[str, str], **kwargs) -> Panel:
        return md_panel(
            comment["body"],
            title=" ".join(
                map(lambda x: get_val(comment, x), ["state", "author", "createdAt"])
            ),
            border_style=""
            + (
                "green"
                if comment.get("isResolved") or comment.get("outdated") == "False"
                else "red"
                if "isResolved" in comment or comment.get("outdated")
                else state_map.get(comment.get("state") or "") or ""
            ),
            **kwargs,
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
            title=kwargs.get("title") or "",
        )

    def fmt_add_del(file: JSONDict) -> List[str]:
        additions = f"-{file['additions']}" if file["additions"] else ""
        deletions = f"-{file['deletions']}" if file["deletions"] else ""
        return [
            wrap(additions.rjust(5), "b green"),
            wrap(deletions.rjust(3), "b red"),
            wrap(file["path"], "b"),
        ]

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
    exclude = {"title", "body", "reviews", "comments", "reviewThreads", "url", "files"}
    pr = data[0]
    pr["diff"] = "[green]+{}[/] [red]-{}[/]".format(
        pr.pop("additions", ""), pr.pop("deletions", "")
    )
    FIELDS_MAP.update(
        {
            "author": format_with_color,
            "participants": lambda x: "  ".join(map(format_with_color, x)),
            "state": lambda x: wrap(wrap(x, "b"), state_map.get(x, "default")),
            "reviewDecision": lambda x: wrap(wrap(x, "b"), state_map.get(x, "default")),
            "isReadByViewer": lambda x: wrap(str(x), state_map.get(str(x), "default")),
            "updatedAt": lambda x: time2human(x, pad=False, use_colors=True),
            "createdAt": lambda x: time2human(x, pad=False, use_colors=True),
            "repository": lambda x: x.get("name"),
            "files": lambda x: border_panel(
                new_table(rows=map(fmt_add_del, x)), title="files"
            ),
        }
    )

    yield ""
    yield Rule(wrap(pr.get("title", " "), "b"))
    keys = sorted(set(pr) - exclude)
    info_table = Group(
        new_table(rows=map(lambda x: (wrap(x, "b"), get_val(pr, x)), keys)),
        get_val(pr, "files"),
    )
    yield new_table(rows=[[simple_panel(info_table), md_panel(pr["body"])]])

    for review in pr["reviews"]:
        for comment in review["comments"]:
            comment["state"] = review["state"]

    global_comments: List[ConsoleRenderable] = []
    raw_global_comments = filter(op.itemgetter("body"), pr["reviews"] + pr["comments"])
    for comment in sorted(raw_global_comments, key=op.itemgetter("createdAt")):
        subtitle = format_with_color("review" if "state" in comment else "comment")
        global_comments.append(comment_panel(comment, subtitle=subtitle))
    yield border_panel(
        new_table(rows=it.zip_longest(*(iter(global_comments),) * 2)),
        title="Reviews & Comments",
    )

    all_comments = it.chain(*map(op.itemgetter("comments"), pr.get("reviews", [])))
    files: List[ConsoleRenderable] = []
    for file, comments in it.groupby(
        sorted(all_comments, key=op.itemgetter("path", "diffHunk", "createdAt")),
        op.itemgetter("path"),
    ):
        for diff_hunk, comments in it.groupby(comments, op.itemgetter("diffHunk")):
            files.append(
                simple_panel(
                    Group(syntax_panel(diff_hunk, "diff"), *map(comment_panel, comments)),
                    title=wrap(file, "b magenta"),
                )
            )
    yield new_table(rows=it.zip_longest(*(iter(files),) * 2))


def lights_table(lights: List[JSONDict]) -> Table:
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


def calendar_table(events: List[JSONDict]) -> Iterable[ConsoleRenderable]:
    def get_start_end(start: datetime, end: datetime) -> Tuple[int, int]:
        if start.hour == end.hour == 0:
            return 0, 86400
        day_start_ts = start.replace(hour=0).timestamp()
        return int(start.timestamp() - day_start_ts), int(end.timestamp() - day_start_ts)

    calendars = set(map(op.itemgetter("calendar"), events))
    cal_to_color = dict(zip(calendars, map(predictably_random_color, calendars)))
    cal_fmted = it.starmap(
        lambda x, y: wrap(f" {x} ", f"b black on {y}"), cal_to_color.items()
    )
    print(Columns(cal_fmted, expand=True, equal=True, align="center"))

    new_events: List[JSONDict] = []
    for event in events:
        orig_start = parse(event["start"])
        orig_end = parse(event["end"])
        h_after_midnight = (
            24 * (orig_end - orig_start).days + ((orig_end - orig_start).seconds // 3600)
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
            if start == end:
                continue

            color = (
                "grey7"
                if end.replace(tzinfo=None) < datetime.now()
                else cal_to_color[event["calendar"]]
            )
            new_events.append(
                {
                    **event,
                    **dict(
                        color=color,
                        summary=wrap(
                            event["summary"], f"b {cal_to_color[event['calendar']]}"
                        ),
                        start=start,
                        start_day=f"{start.day} {start.strftime('%a')}",
                        start_time=wrap(start.strftime("%H:%M"), "white"),
                        end_time=wrap(end.strftime("%H:%M"), "white"),
                        bar=Bar(86400, *get_start_end(start, end), color=color),
                    ),
                }
            )

    keys = "start_day", "summary", "start_time", "end_time", "bar"
    for month, day_events in it.groupby(
        new_events, lambda x: (x["start"].month, x["start"].strftime("%B"))
    ):
        table = new_table(
            *keys,
            expand=True,
            highlight=False,
            padding=0,
            collapse_padding=True,
            show_header=False,
            title_justify="left",
        )
        for event in day_events:
            if "Week " in event["summary"]:
                table.add_row("")
                table.take_dict_item(event, style=event["color"] + " on grey7")
            else:
                table.take_dict_item(event)
        yield border_panel(table, title=month[1])


def tasks_table(tasks: List[JSONDict]) -> None:
    get_time = partial(time2human, use_colors=True, pad=False)
    fields_map: JSONDict = dict(
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
                l,
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
    return flexitable(data)


@draw_data.register(list)
def _draw_data_list(data: List[JSONDict], title: str = "") -> None:
    calls: Dict[str, Callable] = {
        "Pull Requests": pulls_table,
        "Hue lights": lights_table,
        "Calendar": calendar_table,
        "Album": albums_table,
        "Music": tracks_table,
        "Tasks": tasks_table,
        "": flexitable,
    }
    try:
        func = calls[title]
    except KeyError:
        return flexitable(data)
    else:
        ret = func(data)
    return ret


def main():
    args = set()
    if len(sys.argv) > 1:
        args.update(sys.argv[1:])

    data = load_data()
    if "-j" in args:
        console.print_json(data=data)
    else:
        try:
            ret = draw_data(data)
        except Exception as exc:
            console.print(data)
            console.print_exception(extra_lines=4, show_locals=True)
            raise exc
        else:
            if isinstance(ret, Iterable):
                for rend in ret:
                    print(rend)
            else:
                console.print(ret)


if __name__ == "__main__":
    main()
