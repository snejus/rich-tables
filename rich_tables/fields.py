from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, MutableMapping
from contextlib import suppress
from datetime import datetime, timezone
from functools import singledispatch
from itertools import islice
from typing import TYPE_CHECKING, Any, Callable

from rich.text import Text

from .diff import pretty_diff
from .utils import (
    BOLD_GREEN,
    BOLD_RED,
    HashableDict,
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


MATCH_COUNT_HEADER = re.compile(r"duration|(?:_sum$|_?count$)")
MAX_BPM_COLOR = (("green", 135), ("yellow", 165), ("red", 400))


def add_count_bars(
    data: tuple[HashableDict, ...], count_key: str
) -> tuple[HashableDict, ...]:
    all_keys = list(data[0].keys())
    subcount_key = next((k for k in all_keys if k.endswith("_subcount")), None)
    if subcount_key:
        new_count_key = f"{subcount_key.removesuffix('_subcount')}/{count_key.removesuffix('_count')}"  # noqa: E501
    else:
        new_count_key = count_key

    all_counts = [float(i[count_key]) for i in data]
    max_value = max(all_counts)

    bar_key = f"{count_key}_bar"
    for item in data:
        subcount = None
        inverse = count_key.endswith("duration")
        count = item[count_key]
        if subcount_key:
            subcount = float(item[subcount_key])
            count_val = f"{subcount}/{count}"
        elif count_key.endswith("duration"):
            count_val = duration2human(count)
        else:
            count_val = str(count)

        item.pop(count_key, None)
        item[new_count_key] = count_val
        item[bar_key] = progress_bar(
            end=subcount, width=max_value, size=count, inverse=inverse
        )

    if count_key in {"duration", "total_duration"}:
        data = (
            *data,
            HashableDict(
                {
                    all_keys[0]: "TOTAL",
                    count_key: duration2human(sum(all_counts)),
                    bar_key: "",
                }
            ),
        )

    return data


FIELDS_MAP: MutableMapping[str, Callable[..., RenderableType]] = defaultdict(
    lambda: str,
    diff=lambda x: pretty_diff(*x),
    albumtypes=lambda x: " ".join(
        map(
            format_with_color,
            (
                ("; ".join(x) if isinstance(x, (list, tuple)) else x)
                .replace("compilation", "comp")
                .replace("dj-mix; broadcast", "dj-mix")
                .replace("broadcast; dj-mix", "dj-mix")
            ).split("; "),
        )
    ),
    author=lambda x: (
        format_with_color_on_black(x) if isinstance(x, (str, list, tuple, set)) else x
    ),
    labels=lambda x: (
        wrap(
            "    ".join(wrap(y["name"].upper(), f"#{y['color']}") for y in x),
            "b",
        )
        if isinstance(x, (list, tuple))
        else format_with_color(x.upper())
        if isinstance(x, str)
        else x
    ),
    since=lambda x: (
        x
        if isinstance(x, str)
        else datetime.fromtimestamp(float(x), tz=timezone.utc).strftime("%F %H:%M")
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
    helicopta=lambda x: ":fire: " if x == "1" else "",
    hidden=lambda x: ":shit: " if x == "1" else "",
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
    slug=format_with_color_on_black,
)
fields_by_func: dict[Callable[..., RenderableType], Iterable[str]] = {
    format_with_color: (
        "__typename",
        "album",
        "albumtype",
        "app",
        "app_label",
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
        "kind",
        "label",
        "mastering",
        "media",
        "module",
        "operation",
        "primary",
        "priority",
        "project",
        "reporter",
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
        "client",
        "env",
    ),
    split_with_color: ("genre", "genres"),
    human_dt: (
        "added",
        "committedDate",
        "created",
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
        "Description",
        "desc",
        "doc",
        "content",
        "interview",
        "notes",
        "text",
    ),
}
for func, fields in fields_by_func.items():
    for field in fields:
        FIELDS_MAP[field] = func


def _get_val(value: float | str | None, field: str) -> RenderableType:
    if value is None:
        return "None"

    if field.endswith(".py"):
        return border_panel(syntax(value, "python"), title=field)

    if isinstance(value, str):
        value = format_string(value)
    elif isinstance(value, (int, float)):
        value = str(value)

    if field in FIELDS_MAP:
        with suppress(TypeError):
            return FIELDS_MAP[field](value)

    return value


@singledispatch
def get_val(obj: JSONDict | object, field: str) -> Any:
    """Definition of a generic get_val function."""


@get_val.register
def _(obj: dict, field: str) -> Any:  # type: ignore[type-arg]
    return _get_val(obj.get(field), field)


@get_val.register
def _(obj: object, field: str) -> Any:
    return _get_val(getattr(obj, field, None), field)
