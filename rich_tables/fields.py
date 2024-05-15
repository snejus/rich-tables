import json
import re
from collections import defaultdict
from datetime import datetime
from functools import singledispatch
from itertools import islice
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Union

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .sql import fmt_joins, fmt_ordering
from .utils import (
    BOLD_GREEN,
    BOLD_RED,
    JSONDict,
    NewTable,
    border_panel,
    diff,
    duration2human,
    fmt_time,
    format_string,
    format_with_color,
    format_with_color_on_black,
    get_country,
    human_dt,
    list_table,
    md_panel,
    new_table,
    progress_bar,
    simple_panel,
    split_with_color,
    syntax,
    timestamp2timestr,
    wrap,
)

MATCH_COUNT_HEADER = re.compile(r"duration|(_sum|_?count)$")


def counts_table(data: Iterable[JSONDict]) -> Table:
    count_header = ""
    subcount_header = None
    ordered_headers = []
    for key in data[0]:
        if key.endswith("_subcount"):
            subcount_header = key
        elif MATCH_COUNT_HEADER.search(key):
            if count_header:
                ordered_headers.append(key)
            else:
                count_header = key
        else:
            ordered_headers.append(key)

    all_counts = [float(i[count_header]) for i in data]
    num_type = int if len({c % 1 for c in all_counts}) == 1 else float
    max_value = max(all_counts)

    if subcount_header:
        count_header = f"{subcount_header}/{count_header}".replace(
            "_count", ""
        ).replace("_subcount", "")

    table = new_table(*ordered_headers, count_header, count_header, expand=True)
    for item, count in zip(data, all_counts):
        subcount = None
        inverse = False
        count_val = str(count)
        if subcount_header:
            subcount = float(item[subcount_header])
            count_val = f"{num_type(subcount)}/{num_type(count)}"
        elif "duration" in count_header:
            inverse = True
            if num_type is int:
                count_val = duration2human(count)
        else:
            count_val = str(num_type(count))

        table.add_row(
            *(get_val(item, h) for h in ordered_headers),
            count_val,
            progress_bar(
                end=subcount, width=max_value * 15, size=count * 15, inverse=inverse
            ),
        )
    if count_header in {"duration", "total_duration"}:
        table.caption = "Total " + duration2human(float(sum(all_counts)))
        table.caption_justify = "left"
    return table


FIELDS_MAP: MutableMapping[str, Callable[..., RenderableType]] = defaultdict(
    lambda: str,
    diff=lambda x: Text.from_markup(json.dumps(diff(*x), indent=2).replace('"', "")),
    albumtypes=lambda x: " ".join(
        map(
            format_with_color,
            (
                ("; ".join(x) if isinstance(x, list) else x)
                .replace("compilation", "comp")
                .replace("dj-mix; broadcast", "dj-mix")
                .replace("broadcast; dj-mix", "dj-mix")
            ).split("; "),
        )
    ),
    author=format_with_color_on_black,
    labels=lambda x: (
        wrap("    ".join(wrap(y["name"].upper(), f"#{y['color']}") for y in x), "b")
        if isinstance(x, list)
        else format_with_color(x.upper())
    ),
    avg_last_played=lambda x: human_dt(x, acc=2),
    since=lambda x: (
        x
        if isinstance(x, str)
        else datetime.fromtimestamp(float(x)).strftime("%F %H:%M")
    ),
    dt=lambda x: human_dt(x, acc=5),
    # createdAt=lambda x: x.replace("T", " ").replace("Z", ""),
    # updatedAt=lambda x: x.replace("T", " ").replace("Z", ""),
    wait_per_play=lambda x: wrap(
        " ".join(islice(fmt_time(int(float(x))), 1)), BOLD_GREEN
    ),
    bpm=lambda x: (
        wrap(
            str(x),
            (
                BOLD_GREEN
                if x < 135
                else BOLD_RED
                if x > 230
                else "red"
                if x > 165
                else "yellow"
            ),
        )
        if isinstance(x, int)
        else x
    ),
    length=timestamp2timestr,
    tracktotal=lambda x: (
        (wrap("{}", "b cyan") + "/" + wrap("{}", "b cyan")).format(*x)
        if isinstance(x, Iterable) and not isinstance(x, str)
        else str(x)
    ),
    category=lambda x: "/".join(map(format_with_color, x.split("/"))),
    country=get_country,
    helicopta=lambda x: ":fire: " if x and int(x) else "",
    hidden=lambda x: ":shit: " if x and int(x) else "",
    keywords=format_with_color_on_black,
    ingr=lambda x: simple_panel(format_with_color(x)),
    # content=lambda x: md_panel(x) if isinstance(x, str) else x,
    comments=lambda x: md_panel(
        x.replace("\n0", "\n* 0").replace("\n[", "\n* ["), title="comments"
    ),
    released=lambda x: x.replace("-00", "") if isinstance(x, str) else str(x),
    duration=lambda x: duration2human(x) if isinstance(x, (int, float)) else x,
    # total_duration=duration2human,
    plays=lambda x: wrap(x, BOLD_GREEN),
    skips=lambda x: wrap(x, BOLD_RED),
    # body=lambda x: x + "\n",
    # message=Text,
    new=lambda x: (
        wrap(":heavy_check_mark: ", BOLD_GREEN)
        if x
        else wrap(":cross_mark_button: ", BOLD_RED)
    ),
    link=lambda name: (
        wrap(f" {name} ", "b black on red")
        if name == "blocks"
        else wrap(name, BOLD_RED)
        if name == "is blocked by"
        else name
    ),
    context=lambda x: syntax(x, "python"),
    python=lambda x: syntax(x, "python"),
    CreatedBy=lambda x: syntax(x.replace(";", "\n"), "sh"),
    # sql=sql_table,
    file=lambda x: "/".join(map(format_with_color, x.split("/"))),
    field=lambda x: ".".join(map(format_with_color, x.split("."))),
    # log=lambda x: border_panel(
    #     x, border_style="b i", padding=(0, 2, 0, 2), style="on #232323"
    # ),
    unified_diff=lambda x: syntax(x, "diff"),
    diffHunk=lambda x: syntax(x, "diff"),
    snippet=lambda x: border_panel(syntax(x, "python", indent_guides=True)),
    # traceback=lambda x: border_panel(x),
    # traceback=lambda x: border_panel(syntax(x, "python")),
    # diff=lambda x: Text.from_markup(x) if "[/]" in x else md_panel(x),
    query=lambda x: Text(x, style="bold"),
    joins=lambda x: "\n".join(map(fmt_joins, x.split(", "))),
    order_by=lambda x: " ".join(map(fmt_ordering, re.split(r",\s+", x))),
)
fields_by_func = {
    format_with_color: (
        "__typename",
        "album",
        "albumtype",
        "app",
        "area",
        "assignee",
        "brand",
        "calendar",
        "catalognum",
        # "category",
        "categories",
        "Category",
        "code",
        "data_source",
        "default_start_time",
        "default_end_time",
        "Description",
        "endpoint",
        "entity",
        "environment",
        "epic_key",
        "epic_priority",
        "epic_status",
        "event",
        "from",
        "full_name",
        "group_source",
        "Interests",
        "issuetype",
        "key",
        "kind",
        "label",
        "mastering",
        "media",
        "module",
        "operation",
        "primary",
        "priority",
        "project",
        "short_name",
        "source",
        "status",
        "style",
        "subtask_assignee",
        "subtask_key",
        "subtask_priority",
        "subtask_status",
        "symbol",
        "table",
        "to",
        "tables",
        "type_name",
        "user",
    ),
    split_with_color: ("genre", "genres", "name"),
    human_dt: (
        "added",
        "committedDate",
        # "created",
        # "date",
        "due",
        # "end",
        "entry",
        "first_active",
        "last_active",
        "last_played",
        # "modified",
        "mtime",
        # "start",
        "updated",
        # "count"
    ),
    md_panel: (
        "answer",
        "benefits",
        "bodyHTML",
        # "comment",
        "creditText",
        "description",
        "desc",
        "instructions",
        "interview",
        "notes",
        "text",
    ),
}
for func, fields in fields_by_func.items():
    for field in fields:
        FIELDS_MAP[field] = func

try:
    import sqlparse
except ModuleNotFoundError:
    pass
else:
    FIELDS_MAP["sql"] = lambda x: border_panel(
        Syntax(
            sqlparse.format(
                x,
                indent_columns=True,
                strip_whitespace=True,
                strip_comments=True,
                reindent=True,
                reindent_aligned=False,
            ),
            "sql",
            theme="gruvbox-dark",
            background_color="black",
            word_wrap=True,
        )
    )


DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "last_played": ":timer_clock: ",
    "mtime": "updated",
    "data_source": "source",
    "helicopta": ":helicopter: ",
    "hidden": ":no_entry: ",
    "track_alt": ":cd: ",
    "catalognum": ":pen: ",
    "plays": wrap(":play_button: ", BOLD_GREEN),
    "skips": wrap(":stop_button: ", BOLD_RED),
    "albumtypes": "types",
}


def _get_val(value: Any, field: str) -> Any:
    # return FIELDS_MAP[field](value) if value is not None else ""
    if value is None:
        value = "None"

    if isinstance(value, str):
        value = format_string(value)

    if isinstance(value, (int, float)):
        value = str(value)

    if field not in FIELDS_MAP and field.endswith("_group") and isinstance(value, list):
        return format_with_color(value)

    return FIELDS_MAP[field](value)


@singledispatch
def get_val(obj: Union[JSONDict, object], field: str) -> Any:
    """Definition of a generic get_val function."""


@get_val.register
def _(obj: dict, field: str) -> Any:
    return _get_val(obj.get(field), field)


@get_val.register
def _(obj: object, field: str) -> Any:
    return _get_val(getattr(obj, field, None), field)


def sql_table(data: List[JSONDict]) -> NewTable:
    return list_table((get_val(item["sql"], "sql") for idx, item in enumerate(data)))
