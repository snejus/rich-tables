from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, MutableMapping
from datetime import datetime, timezone
from functools import singledispatch
from itertools import islice
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from multimethod import multidispatch
from rich.console import ConsoleRenderable
from rich.panel import Panel
from rich.text import Text

from .diff import pretty_diff
from .utils import (
    BOLD_GREEN,
    BOLD_RED,
    HashableDict,
    HashableList,
    JSONDict,
    border_panel,
    duration2human,
    fmt_time,
    format_string,
    format_with_color,
    format_with_color_on_black,
    get_country,
    human_dt,
    markdown,
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


MATCH_COUNT_HEADER = re.compile(r"duration|(?:_sum$|(?<![a-z])count$)")
MAX_BPM_COLOR = (("green", 135), ("yellow", 165), ("red", 400))


def add_count_bars(
    data: HashableList[HashableDict], count_key: str
) -> HashableList[HashableDict]:
    all_keys = list(data[0].keys())
    subcount_key = next((k for k in all_keys if k.endswith("_subcount")), None)
    if subcount_key:
        new_count_key = f"{subcount_key.removesuffix('_subcount')}/{count_key.removesuffix('_count') or 'total'}"  # noqa: E501
    else:
        new_count_key = count_key

    for item in data:
        item[count_key] = item.get(count_key, 0)
        if subcount_key:
            item[subcount_key] = item[subcount_key]

    all_counts = [i.get(count_key, 0) for i in data]
    max_value = max(all_counts)

    bar_key = f"{new_count_key}_bar"
    for item in data:
        subcount = None
        inverse = count_key.endswith("duration")
        count = item.get(count_key, 0)
        if count_key.endswith("duration"):
            count_val = duration2human(count)
        else:
            count_val = str(int(count))

        if subcount_key:
            subcount = item[subcount_key]
            count_val = f"{subcount}/{count}"

        # item.pop(count_key, None)
        item[new_count_key] = count_val
        item[bar_key] = progress_bar(
            end=subcount, width=max_value, size=count, inverse=inverse
        )

    if count_key in {"duration", "total_duration"}:
        data.append(
            HashableDict(
                {
                    all_keys[0]: "TOTAL",
                    count_key: duration2human(sum(all_counts)),
                    bar_key: "",
                }
            )
        )

    return data


TD = TypeVar("TD", bound=dict[str, Any])


@multidispatch
def comment_panel(content: str | TD, **kwargs) -> Panel:
    raise NotImplementedError


@comment_panel.register
def _comment_panel_str(content: str, **kwargs) -> Panel:
    if m := re.match(r"\[title\](.+?)\[/title\]\s+", content):
        kwargs["title"] = m[1]
        content = content.replace(m[0], "")

    content = content.replace("- [x]", "* :ballot_box_with_check:")

    return border_panel(markdown(content), **kwargs)


@comment_panel.register
def _comment_panel_dict(content: TD, **kwargs) -> Panel:
    body = content.pop("body")
    title = " ".join(_get_val(v, k) for k, v in content.items())

    return comment_panel(body, title=title)


FIELDS_MAP: MutableMapping[str, Callable[..., RenderableType]] = defaultdict(
    lambda: str,
    diff=lambda x: pretty_diff(*x),
    albumtypes=lambda x: " ".join(
        map(
            format_with_color,
            (
                ("; ".join(x) if isinstance(x, (list, HashableList, tuple)) else x)
                .replace("compilation", "comp")
                .replace("dj-mix; broadcast", "dj-mix")
                .replace("broadcast; dj-mix", "dj-mix")
            ).split("; "),
        )
    ),
    author=lambda x: (
        format_with_color_on_black(x)
        if isinstance(x, (str, list, HashableList, tuple, set))
        else x
    ),
    labels=lambda x: (
        wrap(" ".join(wrap(y["name"], f"#{y['color']}") for y in x), "b")
        if isinstance(x, (list, HashableList, tuple))
        else format_with_color(x)
        if isinstance(x, str)
        else ""
        if x is None
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
    helicopta=lambda x: ":fire: " if x == 1 else "",
    hidden=lambda x: ":shit: " if x == 1 else "",
    keywords=format_with_color_on_black,
    ingr=lambda x: simple_panel(format_with_color(x)),
    # members=lambda x: " ".join(
    #     wrap(wrap(a, clr), f"on {clr}")
    #     for a in x
    #     if (
    #         clr := predictably_random_color(
    #             "".join(chr(int(a[i : i + 3])) for i in range(0, len(a), 3))
    #         )
    #     )
    # ),
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
    code=lambda x: syntax(x, "python") if isinstance(x, str) else x,
    context=lambda x: syntax(x, "python"),
    python=lambda x: syntax(x, "python"),
    CreatedBy=lambda x: syntax(x.replace(";", "\n"), "sh"),
    file=lambda x: "/".join(map(format_with_color, x.split("/"))),
    field=lambda x: ".".join(map(format_with_color, x.split("."))),
    text=lambda x: syntax(x, "markdown"),
    unified_diff=lambda x: syntax(x, "diff"),
    diffHunk=lambda x: syntax(x, "diff"),
    snippet=lambda x: border_panel(syntax(x, "python", indent_guides=True)),
    query=lambda x: Text(x, style="bold"),
    sql=lambda x: sql_syntax("---\n\n" + x.replace(r"\[", "[")),
    # created_at=lambda x: f"[white]{x.replace('T', ' ').replace('Z', '')}[/]",
    comment=comment_panel,
    parent_id=format_with_color_on_black,
    slug=format_with_color_on_black,
)
fields_by_func: dict[Callable[..., RenderableType], Iterable[str]] = {
    format_with_color: (
        "__typename",
        "action",
        "album",
        "albumtype",
        "allowedValues",
        "app",
        "app_label",
        "area",
        "artists",
        "assignee",
        "brand",
        "calendar",
        "catalognum",
        "categories",
        "Category",
        "classname",
        "clinician",
        "data_source",
        "default_start_time",
        "default_end_time",
        "departments",
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
        "ticker",
        "type",
        "type_name",
        "user",
        "client",
        "env",
    ),
    split_with_color: ("genre", "genres", "Interests"),
    human_dt: (
        "added",
        "committedDate",
        "created",
        "created_at",
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
        "sunrise",
        "sunset",
        "updated_at",
    ),
    md_panel: (
        "answer",
        "benefits",
        "body",
        "bodyHTML",
        "comments",
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


def _get_val(value: float | str | RenderableType | None, field: str) -> RenderableType:
    if value is None:
        return ""

    if field.endswith(".py"):
        return border_panel(syntax(value, "python"), title=field)

    if isinstance(value, ConsoleRenderable):
        return value

    if field in FIELDS_MAP:
        return FIELDS_MAP[field](value)

    if isinstance(value, str):
        value = format_string(value)

    return str(value)


@singledispatch
def get_val(obj: JSONDict | object, field: str) -> Any:
    """Definition of a generic get_val function."""


@get_val.register
def _(obj: dict, field: str) -> Any:  # type: ignore[type-arg]
    return _get_val(obj.get(field), field)


@get_val.register
def _(obj: object, field: str) -> Any:
    return _get_val(getattr(obj, field, None), field)
