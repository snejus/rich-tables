import itertools as it
import json
import operator as op
import re
import sys
import typing as t
from datetime import datetime, timedelta
from functools import singledispatch

from rich import box
from rich.align import Align
from rich.bar import Bar
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from rich_tables.generic import flexitable
from rich_tables.music import albums_table
from rich_tables.utils import (
    FIELDS_MAP,
    border_panel,
    colored_with_bg,
    format_with_color,
    get_val,
    make_console,
    make_difftext,
    md_panel,
    new_table,
    new_tree,
    predictably_random_color,
    progress_bar,
    simple_panel,
    time2human,
    wrap,
)

JSONDict = t.Dict[str, t.Any]
GroupsDict = t.Dict[str, t.List]


console = make_console()
print = console.print


def pulls_table(data: t.List[JSONDict]) -> t.Iterable[t.Union[str, ConsoleRenderable]]:
    def res_border_style(resolved: bool, outdated: bool) -> str:
        return "green" if resolved else "yellow" if resolved is False else ""

    def comment_panel(comment: JSONDict, **kwargs) -> Panel:
        reactions = [
            wrap(f":{r['content'].lower()}:", "bold") + " " + get_val(r, "user")
            for r in comment.get("reactions", [])
        ]
        text = comment["body"]
        split = re.split(r"(?=```.*)```", text)
        rends = []
        # table = new_table()
        for idx, content in enumerate(split):
            if content:
                if idx % 2 == 0:
                    content = md_panel(content)
                else:
                    lang, codeblock = content.split("\n", 1)
                    content = FIELDS_MAP[lang or "python"](text)
                # table.add_row(content)
                rends.append(content)
        return simple_panel(
            Group(*rends),
            **{
                "title": " ".join(get_val(comment, f) for f in ["author", "createdAt"]),
                "subtitle": "\n".join(reactions) + "\n",
                **kwargs,
            },
        )

    def fmt_add_del(file: JSONDict) -> t.List[str]:
        added, deleted = file["additions"], file["deletions"]
        additions = f"+{added}" if added else ""
        deletions = f"-{deleted}" if deleted else ""
        return [wrap(additions.rjust(5), "b green"), wrap(deletions.rjust(3), "b red")]

    def state_color(state: str) -> str:
        return {
            "True": "green",
            True: "green",
            "APPROVED": "green",
            "RESOLVED": "s green",
            "OPEN": "green",
            "MERGED": "magenta",
            "PENDING": "yellow",
            "OUTDATED": "yellow",
            "COMMENTED": "yellow",
            "CHANGES_REQUESTED": "yellow",
            "REVIEW_REQUIRED": "red",
            "DISMISSED": "gray42",
            "False": "red",
        }.get(state, "default")

    def fmt_state(state: str) -> str:
        return wrap(state, state_color(state))

    exclude = {
        "title",
        "body",
        "reviews",
        "comments",
        "reviewThreads",
        "url",
        "files",
        "commits",
        "isReadByViewer",
        "repository",
        "labels",
        "reviewDecision",
        "state",
        "reviewRequests",
    }
    FIELDS_MAP.update(
        {
            "state": lambda x: wrap(fmt_state(x), "b"),
            "reviewDecision": lambda x: wrap(fmt_state(x), "b"),
            "dates": lambda x: new_table(
                rows=[
                    [wrap(r" ⬤ ", "b green"), time2human(x[0])],
                    [wrap(r" ◯ ", "b yellow"), time2human(x[1])],
                ]
            ),
            "repository": lambda x: x.get("name"),
            "path": lambda x: wrap(x, "b"),
            "message": lambda x: wrap(x, "i"),
            "files": lambda x: border_panel(
                new_table(
                    rows=[
                        [*fmt_add_del(y), get_val(y, "path")]
                        for y in sorted(
                            x,
                            key=lambda x: x["additions"] + x["deletions"],
                            reverse=True,
                        )
                    ]
                ),
                title="files",
                border_style=f"dim {predictably_random_color('files')}",
            ),
            "commits": lambda x: border_panel(
                new_table(
                    rows=[
                        [
                            *fmt_add_del(y),
                            get_val(y, "message"),
                            get_val(y, "committedDate"),
                        ]
                        for y in x
                    ]
                ),
                title="commits",
                border_style=f"dim {predictably_random_color('commits')}",
            ),
            "reviewRequests": lambda x: "  ".join(map(colored_with_bg, x)),
        }
    )

    pr = data[0]
    if pr and "additions" in pr:
        pr["files"].append(
            dict(additions=pr.pop("additions", ""), deletions=pr.pop("deletions", ""))
        )
    pr["dates"] = {"created": pr.pop("createdAt"), "updated": pr.pop("updatedAt")}

    title, name = pr["title"], pr["repository"]["name"]
    repo_color = predictably_random_color(name)
    decision_color = state_color(pr["reviewDecision"])
    keys = sorted(set(pr) - exclude)
    yield border_panel(
        new_table(
            rows=[
                [Align.center(wrap(title, state_color(pr["state"])))],
                [Align.center(get_val(pr, "labels"), vertical="middle")],
                [flexitable([{k: v for k, v in pr.items() if k in keys}])]
                # [
                #     Columns(
                #         map(
                #             lambda x: simple_panel(
                #                 get_val(pr, x),
                #                 title=wrap(x, "b"),
                #                 title_align="center",
                #                 expand=True,
                #                 align="center",
                #             ),
                #             keys,
                #         ),
                #         align="center",
                #         expand=True,
                #         equal=True,
                #     )
                # ],
            ]
        ),
        title=wrap(name, f"b {repo_color}"),
        box=box.DOUBLE_EDGE,
        border_style=decision_color,
        subtitle=f"[b][{decision_color}]{pr['reviewDecision']}[/] [#ffffff]//[/] {fmt_state(pr['state'])}[/]",
        expand=False,
        align="center",
        title_align="center",
        subtitle_align="center",
    )

    yield md_panel(pr["body"])
    yield new_table(rows=[[get_val(pr, "files"), get_val(pr, "commits")]])

    global_comments: t.List[ConsoleRenderable] = []
    raw_global_comments = pr["comments"] + pr["reviews"]
    for comment in sorted(raw_global_comments, key=op.itemgetter("createdAt")):
        state = comment.get("state", "COMMENTED")
        subtitle = "comment"
        if state != "COMMENTED":
            subtitle = "review - " + wrap(state, f"b {state_color(state)}")
        if state != "COMMENTED" or comment["body"]:
            global_comments.append(
                comment_panel(
                    comment,
                    subtitle=subtitle,
                    border_style=predictably_random_color(comment["author"]),
                    box=box.HEAVY,
                )
            )
    if global_comments:
        yield border_panel(
            new_table(rows=[[x] for x in global_comments]), title="Reviews & Comments"
        )

    yield new_table(rows=[[get_val(pr, "reviewRequests")]])
    total_threads = len(pr["reviewThreads"])
    if not total_threads:
        return

    resolved_threads = len(list(filter(lambda x: x["isResolved"], pr["reviewThreads"])))
    table = new_table()
    table.add_row(
        border_panel(
            progress_bar(resolved_threads, total_threads),
            title=f"{resolved_threads} / {total_threads} resolved",
            border_style="dim yellow",
        )
    )

    for thread in pr["reviewThreads"]:
        files: t.List[ConsoleRenderable] = []
        for diff_hunk, comments in it.groupby(
            sorted(
                thread["comments"],
                key=lambda x: (x.get("diffHunk", ""), x.get("createdAt", "")),
            ),
            lambda x: x.get("diffHunk"),
        ):
            rows = it.chain.from_iterable(
                [[x], [""]] for x in map(comment_panel, comments)
            )
            comments_col = new_table(rows=rows)
            diff = Syntax(
                diff_hunk,
                "diff",
                theme="paraiso-dark",
                background_color="black",
                word_wrap=True,
            )
            files.append(new_table(rows=[[diff, simple_panel(comments_col)]]))

        table.add_row(
            border_panel(
                new_table(rows=it.zip_longest(*(iter(files),) * 2)),
                border_style=res_border_style(
                    thread["isResolved"], thread["isOutdated"]
                ),
                title=wrap(thread["path"], "b magenta")
                + " "
                + fmt_state("RESOLVED" if thread["isResolved"] else "PENDING"),
                subtitle=fmt_state("OUTDATED") if thread["isOutdated"] else "",
            )
        )
    yield border_panel(table)


def lights_table(lights: t.List[JSONDict]) -> Table:
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
        table.add_row(
            *map(str, map(lambda x: light.get(x) or "", headers)), style=style
        )
    return table


def calendar_table(events: t.List[JSONDict]) -> t.Iterable[ConsoleRenderable]:
    def get_start_end(start: datetime, end: datetime) -> t.Tuple[int, int]:
        if start.hour == end.hour == 0:
            return 0, 86400
        day_start_ts = start.replace(hour=0).timestamp()
        return int(start.timestamp() - day_start_ts), int(
            end.timestamp() - day_start_ts
        )

    status_map = dict(
        needsAction="[b grey3] ? [/]",
        accepted="[b green] ✔ [/]",
        declined="[b red] ✖ [/]",
        tentative="[b yellow] ? [/]",
    )

    calendars = set(map(op.itemgetter("calendar"), events))
    cal_to_color = dict(zip(calendars, map(predictably_random_color, calendars)))
    cal_fmted = it.starmap(
        lambda x, y: wrap(f" {x} ", f"b black on {y}"), cal_to_color.items()
    )
    yield Columns(cal_fmted, expand=True, equal=False, align="center")

    new_events: t.List[JSONDict] = []
    for event in events:
        start_iso, end_iso = event["start"], event["end"]
        orig_start = datetime.fromisoformat(
            start_iso.get("dateTime", start_iso.get("date"))
        )
        orig_end = datetime.fromisoformat(end_iso.get("dateTime", end_iso.get("date")))
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
                        summary=status_map[event["status"]]
                        + wrap(
                            event["summary"] or "busy",
                            f"b {cal_to_color[event['calendar']]}",
                        ),
                        start=start,
                        start_day=start.strftime("%d %a"),
                        start_time=wrap(start.strftime("%H:%M"), "white"),
                        end_time=wrap(end.strftime("%H:%M"), "white"),
                        bar=Bar(86400, *get_start_end(start, end), color=color),
                    ),
                }
            )

    keys = "summary", "start_time", "end_time", "bar"
    for month, month_events in it.groupby(
        new_events, lambda x: (x["start"].month, x["start"].strftime("%Y %B"))
    ):
        table = new_table(*keys, highlight=False, padding=0, show_header=False)
        for day, day_events in it.groupby(
            sorted(month_events, key=lambda x: x["start_day"]), lambda x: x["start_day"]
        ):
            table.add_row(wrap(day, "b i"))
            for event in day_events:
                if "Week " in event["summary"]:
                    table.add_row("")
                    table.add_dict_item(event, style=event["color"] + " on grey7")
                else:
                    table.add_dict_item(event)
            table.add_row("")
        yield border_panel(table, title=month[1])


def tasktime(datestr: str):
    return time2human(datetime.strptime(datestr, "%Y%m%dT%H%M%SZ").timestamp())


def tasks_table(tasks: t.List[JSONDict]) -> t.Iterator:
    fields_map: JSONDict = dict(
        id=str,
        urgency=lambda x: str(round(x, 1)),
        description=lambda x: x,
        due=tasktime,
        end=tasktime,
        sched=tasktime,
        tags=lambda x: " ".join(map(format_with_color, x or [])),
        project=format_with_color,
        modified=tasktime,
        annotations=lambda l: "\n".join(
            map(
                lambda x: wrap(tasktime(x["entry"]), "b")
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
    headers = ["urgency", "id"] + [k for k in fields_map.keys() if k != group_by]

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
        yield panel(table, title=wrap(group, "b"), style=project_color)


def load_data() -> t.Any:
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
def draw_data(data: t.Union[JSONDict, t.List], title: str = "") -> None:
    pass


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict) -> t.Iterator:
    if "values" in data and "title" in data:
        values, title = data["values"], data["title"]
        calls: t.Dict[str, t.Callable] = {
            "Pull Requests": pulls_table,
            # "Hue lights": lights_table,
            "Calendar": calendar_table,
            "Album": albums_table,
            "Tasks": tasks_table,
        }
        if title in calls:
            yield from calls[title](values)
        else:
            yield flexitable(values)
    else:
        yield flexitable(data)


@draw_data.register(list)
def _draw_data_list(data: t.List[JSONDict], title: str = "") -> t.Iterator:
    yield flexitable(data)


def main():
    args = []
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])

    if args and args[0] == "diff":
        console.print(make_difftext(*args[1:]))
        return

    if "-s" in set(args):
        console.record = True

    data = load_data()
    if "-j" in args:
        console.print_json(data=data)
    else:
        try:
            for ret in draw_data(data):
                console.print(ret)
        except Exception:
            console.print_exception(show_locals=True)

    if "-s" in set(args):
        console.save_html("saved.html")


if __name__ == "__main__":
    main()
