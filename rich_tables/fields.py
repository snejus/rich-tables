from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from functools import singledispatch
from itertools import islice
from typing import TYPE_CHECKING, Any, Callable, Iterable, MutableMapping

from rich.text import Text

from .utils import (
    BOLD_GREEN,
    BOLD_RED,
    JSONDict,
    border_panel,
    duration2human,
    fmt_time,
    format_string,
    format_with_color,
    format_with_color_on_black,
    get_country,
    human_dt,
    md_panel,
    new_table,
    pretty_diff,
    progress_bar,
    simple_panel,
    split_with_color,
    sql_syntax,
    syntax,
    timestamp2timestr,
    wrap,
)

if TYPE_CHECKING:
    from rich.console import RenderableType
    from rich.table import Table


MATCH_COUNT_HEADER = re.compile(r"duration|(_sum$|_?count$)")
MAX_BPM_COLOR = (("green", 135), ("yellow", 165), ("red", 400))


def add_count_bars(data: list[JSONDict]) -> list[JSONDict]:
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

    all_counts = [float(i.get(count_header, 0)) for i in data]
    num_type = int if len({c % 1 for c in all_counts}) == 1 else float
    max_value = max(all_counts)

    if subcount_header:
        count_header = f"{subcount_header}/{count_header}".replace(
            "_count", ""
        ).replace("_subcount", "")

    keys = ordered_headers
    new_data = []
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

        new_item = {k: item.get(k) for k in keys}
        new_item[count_header] = count_val
        new_item[f"{count_header}_bar"] = progress_bar(
            end=subcount, width=max_value, size=count, inverse=inverse
        )
        new_data.append(new_item)

    if count_header in {"duration", "total_duration"}:
        new_data.append({
            keys[0]: "TOTAL",
            count_header: duration2human(float(sum(all_counts))),
        })

    return new_data


def counts_table(data: list[JSONDict]) -> Table:
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

    all_counts = [float(i.get(count_header, 0)) for i in data]
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
            progress_bar(end=subcount, width=max_value, size=count, inverse=inverse),
        )
    if count_header in {"duration", "total_duration"}:
        table.caption = f"Total {duration2human(float(sum(all_counts)))}"
        table.caption_justify = "left"
    return table


FIELDS_MAP: MutableMapping[str, Callable[..., RenderableType]] = defaultdict(
    lambda: str,
    diff=lambda x: pretty_diff(*x),
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
        wrap(
            "    ".join(wrap(y["name"].upper(), f"#{y['color']}") for y in x),
            "b",
        )
        if isinstance(x, list)
        else format_with_color(x.upper())
        if isinstance(x, str)
        else x
    ),
    since=lambda x: (
        x
        if isinstance(x, str)
        else datetime.fromtimestamp(float(x)).strftime("%F %H:%M")
    ),
    wait_per_play=lambda x: wrap(
        " ".join(islice(fmt_time(int(float(x))), 1)), BOLD_GREEN
    ),
    bpm=lambda x: (
        wrap(str(x), next(c for c, m in MAX_BPM_COLOR if x < m))
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
    helicopta=lambda x: (":fire: " if int(x) else "") if str(x).isdigit() else x,
    hidden=lambda x: (":shit: " if int(x) else "") if str(x).isdigit() else x,
    keywords=format_with_color_on_black,
    ingr=lambda x: simple_panel(format_with_color(x)),
    comments=lambda x: md_panel(
        x.replace("\n0", "\n* 0").replace("\n[", "\n* ["), title="comments"
    ),
    released=lambda x: x.replace("-00", "") if isinstance(x, str) else str(x),
    duration=lambda x: duration2human(x) if isinstance(x, (int, float)) else x,
    plays=lambda x: wrap(x, BOLD_GREEN),
    skips=lambda x: wrap(x, BOLD_RED),
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
    code=lambda x: syntax(x, "python"),
    context=lambda x: syntax(x, "python"),
    python=lambda x: syntax(x, "python"),
    CreatedBy=lambda x: syntax(x.replace(";", "\n"), "sh"),
    file=lambda x: "/".join(map(format_with_color, x.split("/"))),
    field=lambda x: ".".join(map(format_with_color, x.split("."))),
    unified_diff=lambda x: syntax(x, "diff"),
    diffHunk=lambda x: syntax(x, "diff"),
    snippet=lambda x: border_panel(syntax(x, "python", indent_guides=True)),
    query=lambda x: Text(x, style="bold"),
    sql=lambda x: border_panel(sql_syntax(x.replace(r"\[", "["))),
)
fields_by_func: dict[Callable[..., RenderableType], Iterable[str]] = {
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
        "categories",
        "Category",
        "classname",
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
        # "name",
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
        "test",
        "type",
        "type_name",
        "user",
    ),
    split_with_color: ("genre", "genres"),
    human_dt: (
        "added",
        "committedDate",
        "due",
        "done_date",
        "start",
        "end",
        "entry",
        "first_active",
        "last_active",
        "last_played",
        "mtime",
        "updated",
        "providerPublishTime",
        "release_date",
    ),
    md_panel: (
        "answer",
        "benefits",
        "body",
        "bodyHTML",
        "creditText",
        "description",
        "desc",
        # "instructions",
        "content",
        "interview",
        "notes",
        "text",
    ),
}
for func, fields in fields_by_func.items():
    for field in fields:
        FIELDS_MAP[field] = func

DISPLAY_HEADER: dict[str, str] = {
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
    if value is None:
        return "None"

    if field.endswith(".py"):
        return border_panel(syntax(value, "python"), title=field)

    if isinstance(value, str):
        value = format_string(value)

    if isinstance(value, (int, float)):
        value = str(value)

    if field in FIELDS_MAP:
        try:
            return FIELDS_MAP[field](value)
        except TypeError:
            return value

    if field.endswith("_group") and isinstance(value, list):
        return format_with_color(value)

    return value


@singledispatch
def get_val(obj: JSONDict | object, field: str) -> Any:
    """Definition of a generic get_val function."""


@get_val.register
def _(obj: dict, field: str) -> Any:
    return _get_val(obj.get(field), field)


@get_val.register
def _(obj: object, field: str) -> Any:
    return _get_val(getattr(obj, field, None), field)
