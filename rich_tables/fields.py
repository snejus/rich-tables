import json
import re
from collections import defaultdict
from datetime import datetime
from functools import singledispatch
from itertools import islice, product
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Type, Union

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .sql import fmt_joins, fmt_ordering
from .utils import (
    BOLD_GREEN,
    BOLD_RED,
    JSONDict,
    border_panel,
    colored_split,
    colored_with_bg,
    diff,
    duration2human,
    fmt_time,
    format_with_color,
    get_country,
    md_panel,
    new_table,
    progress_bar,
    simple_panel,
    syntax,
    time2human,
    timestamp2timestr,
    wrap,
)


def counts_table(data: List[JSONDict], count_key: str, header: str = "") -> Table:
    keys = dict.fromkeys(data[0])

    all_counts = {float(i.get(count_key) or 0) for i in data}
    num_type: Type = float
    if len({c % 1 for c in all_counts}) == 1:
        num_type = int
    total_max = max(all_counts)

    # ensure count_col is at the end
    headers = [k for k in keys if k not in {count_key, "total"}]
    table = new_table(*headers, count_key, "")
    for item in data:
        item_count = float(item.pop(count_key) or 0)
        item_max = item.pop("total", None)
        if item_max is not None:
            item_max = float(item_max)
            item_table_val = f"{num_type(item_count)}/{num_type(item_max)}"
        elif "duration" in count_key:
            item_table_val = duration2human(item_count)
        else:
            item_table_val = str(num_type(item_count))
        table.add_row(
            *(get_val(item, h) for h in headers),
            item_table_val,
            progress_bar(item_count, total_max, item_max=item_max),
        )
    if count_key in {"duration", "total_duration"}:
        table.caption = "Total " + duration2human(float(sum(all_counts)))
        table.caption_justify = "left"
    if header:
        table.title = header
    return table


FIELDS_MAP: MutableMapping[str, Callable[..., RenderableType]] = defaultdict(
    lambda: str,
    # diff=lambda x: Text.from_markup(json.dumps(diff(*x), indent=2).replace('"', "")),
    albumtypes=lambda x: "; ".join(
        map(
            format_with_color,
            {
                "album; compilation": "comp",
                "dj-mix; broadcast": "dj-mix",
                "broadcast; dj-mix": "dj-mix",
            }
            .get(x, x)
            .split("; "),
        )
    ),
    author=colored_with_bg,
    labels=lambda x: (
        wrap("    ".join(wrap(y["name"].upper(), f"#{y['color']}") for y in x), "b i")
        if isinstance(x, list)
        else colored_split(x)
    ),
    avg_last_played=lambda x: time2human(x, acc=2),
    since=lambda x: (
        x
        if isinstance(x, str)
        else datetime.fromtimestamp(float(x)).strftime("%F %H:%M")
    ),
    dt=lambda x: time2human(x, 5),
    createdAt=lambda x: x.replace("T", " ").replace("Z", ""),
    updatedAt=lambda x: x.replace("T", " ").replace("Z", ""),
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
    group_source=lambda x: ", ".join(map(format_with_color, x)),
    length=timestamp2timestr,
    tracktotal=lambda x: (
        (wrap("{}", "b cyan") + "/" + wrap("{}", "b cyan")).format(*x)
        if isinstance(x, Iterable) and not isinstance(x, str)
        else str(x)
    ),
    country=get_country,
    helicopta=lambda x: ":fire: " if x and int(x) else "",
    hidden=lambda x: ":shit: " if x and int(x) else "",
    keywords=lambda x: (
        " ".join(map(colored_with_bg, colored_split(x).split("  ")))
        if isinstance(x, str)
        else x
    ),
    ingr=lambda x: simple_panel(colored_split(x)),
    content=lambda x: md_panel(x) if isinstance(x, str) else x,
    comments=lambda x: md_panel(
        x.replace("\n0", "\n* 0").replace("\n[", "\n* ["), title="comments"
    ),
    released=lambda x: x.replace("-00", "") if isinstance(x, str) else str(x),
    primary=lambda x: colored_split(x) if isinstance(x, str) else str(x),
    duration=lambda x: duration2human(x) if isinstance(x, (int, float)) else x,
    total_duration=lambda x: duration2human(x),
    plays=lambda x: wrap(x, BOLD_GREEN),
    skips=lambda x: wrap(x, BOLD_RED),
    body=lambda x: x + "\n",
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
    log=lambda x: border_panel(syntax(x, "python", indent_guides=True)),
    unified_diff=lambda x: syntax(x, "diff"),
    diffHunk=lambda x: syntax(x, "diff"),
    # diff=lambda x: Text.from_markup(x) if "[/]" in x else md_panel(x),
    query=lambda x: Text(x, style="bold"),
    joins=lambda x: "\n".join(map(fmt_joins, x.split(", "))),
    order_by=lambda x: " ".join(map(fmt_ordering, re.split(r",\s+", x))),
)
fields_by_func = {
    format_with_color: (
        "album",
        "albumtype",
        "assignee",
        "brand",
        "calendar",
        "catalognum",
        "category",
        "Category",
        "code",
        "data_source",
        "Description",
        "endpoint",
        "entity",
        "environment",
        "epic_key",
        "epic_priority",
        "epic_status",
        "event",
        "from",
        "issuetype",
        "key",
        "label",
        "mastering",
        "media",
        "module",
        "priority",
        "project",
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
        "__typename",
        "type_name",
        "user",
    ),
    time2human: (
        "added",
        "committedDate",
        "# created",
        "due",
        "end",
        "entry",
        "first_active",
        "last_active",
        "last_played",
        "modified",
        "mtime",
        "start",
        "updated",
    ),
    md_panel: (
        "answer",
        "benefits",
        "bodyHTML",
        "# comment",
        "creditText",
        "description",
        "instructions",
        "interview",
        "notes",
        "text",
    ),
    colored_split: ("error", "genre", "kind", "operation", "tables", "tags"),
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
                x.replace('"', ""),
                indent_columns=False,
                strip_whitespace=True,
                strip_comments=True,
                reindent=True,
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
    return FIELDS_MAP[field](value) if value is not None else ""


@singledispatch
def get_val(obj: Union[JSONDict, object], field: str) -> Any:
    """Definition of a generic get_val function."""


@get_val.register
def _(obj: dict, field: str) -> Any:
    return _get_val(obj.get(field), field)


@get_val.register
def _(obj: object, field: str) -> Any:
    return _get_val(getattr(obj, field, None), field)
