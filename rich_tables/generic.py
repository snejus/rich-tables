"""Dynamic table generation for various data types with Rich formatting.

This module provides a flexible system for rendering different Python data types
as rich, formatted tables in the terminal. It uses Rich's rendering capabilities
to display data in structured, visually appealing formats with automatic
adaptation to content complexity and size.

The primary entry point is the `flexitable` multidispatch function which renders
different data types appropriately, with specialized handling for dictionaries,
lists, strings and other types.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from functools import cache, partial, wraps
from operator import itemgetter
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from multimethod import multidispatch
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, RenderableType  # noqa: TC002
from rich.logging import RichHandler
from rich.text import Text
from rich.tree import Tree

from . import fields
from .diff import to_hashable
from .fields import MATCH_COUNT_HEADER, _get_val, add_count_bars
from .utils import (
    HashableDict,
    NewTable,
    border_panel,
    format_with_color,
    list_table,
    make_console,
    new_table,
    new_tree,
    predictably_random_color,
    wrap,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rich.table import Table


T = TypeVar("T")
console = make_console()

MAX_DICT_LENGTH = int(os.getenv("TABLE_MAX_DICT_LENGTH") or 500)


def time_fmt(current: datetime) -> Text:
    diff = current - time_fmt.prev  # type: ignore [attr-defined]
    time_fmt.prev = current  # type: ignore [attr-defined]
    return Text(f"{diff.total_seconds() * 100:.2f}s")


time_fmt.prev = datetime.now(tz=timezone.utc)  # type: ignore [attr-defined]


log = logging.getLogger(__name__)
if not log.handlers:
    handler = RichHandler(
        tracebacks_show_locals=True,
        omit_repeated_times=False,
        show_time=True,
        log_time_format=time_fmt,
    )
    log.addHandler(handler)
    if os.getenv("DEBUG"):
        log.setLevel("DEBUG")


class DebugLogger:
    def __init__(self) -> None:
        self.indent = ""

    def debug(self, _func: Callable[..., T], *args: Any) -> None:
        if log.isEnabledFor(10):
            data, *header = (str(arg).split(r"\n")[0] for arg in args)
            print(
                self.indent
                + " ".join(
                    [
                        f"Function \033[1;31m{_func.__name__}\033[0m",
                        f"Types: \033[1;33m{list(_func.__annotations__.values())[:-1]}\033[0m",  # noqa: E501
                        f"Header: \033[1;35m{header[0]}\033[0m " if header else "",
                        f"Data: \033[1m{data}\033[0m" if data else "",
                    ]
                )
            )
            self.indent += "│ "

    def undebug(self, _type: type) -> None:
        self.indent = self.indent[:-2]
        if log.isEnabledFor(10):
            print(f"{self.indent}└─ " + f"Returning {_type}")


_debug_logger = DebugLogger()


def debug(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any) -> T:
        _debug_logger.debug(func, *args)
        result = func(*args)
        _debug_logger.undebug(type(result))
        return result

    return wrapper


def mapping_view_table() -> NewTable:
    """Return a table with two columns.

    * First for bold field names
    * Second one for values.
    """
    table = new_table(border_style="cyan", style="cyan", box=box.MINIMAL, expand=False)
    table.add_column(style="bold misty_rose1")
    table.add_column()
    table.show_header = False
    return table


def prepare_dict(item: HashableDict) -> HashableDict:
    if "before" in item and "after" in item:
        item["diff"] = (item.pop("before"), item.pop("after"))
    return item


@multidispatch
@cache
@debug
def flexitable(data: Any) -> RenderableType:
    return str(data)


@flexitable.register
@debug
def _list(data: list[Any]) -> RenderableType:
    return flexitable(to_hashable(data))


@flexitable.register
@debug
def _dict(data: dict[str, Any]) -> RenderableType:
    tree = flexitable(to_hashable(data))
    tree.hide_root = True
    return tree


@flexitable.register
@cache
@debug
def _header(data: Any, header: str) -> RenderableType:
    if data in ("", [], {}):
        return ""

    if isinstance(data, HashableDict):
        tree = _json_dict(data)
        tree.label = wrap(header, "b")
        tree.guide_style = f"bold dim {predictably_random_color(str(sorted(data)))}"
        return tree

    if (
        header.endswith(".py") and isinstance(data, str)
    ) or header in fields.FIELDS_MAP:
        return _get_val(data, header)

    if isinstance(data, (list, tuple)):
        return flexitable(data)

    with suppress(AttributeError):
        data = _get_val(data, header)

    if not isinstance(data, str):
        return flexitable(data)

    return data


@flexitable.register
@debug
def _renderable(data: ConsoleRenderable) -> RenderableType:
    return data


@flexitable.register
@cache
@debug
def _str(data: str) -> RenderableType:
    return data


@flexitable.register
@debug
def _json_dict(data: HashableDict) -> Tree:
    data = prepare_dict(data)
    tree = new_tree()
    for key, value in data.items():
        renderable = flexitable(value or "", key)
        header = wrap(key, "b")

        if isinstance(renderable, str):
            renderable = f"{header}: {renderable}"
        elif isinstance(renderable, Tree):
            renderable.guide_style = "bold dim"
        else:
            renderable = new_tree([renderable], key, guide_style="bold dim")

        tree.add(renderable)
    tree.guide_style = f"bold dim {predictably_random_color(str(sorted(data)))}"
    return tree


simple_head_table = partial(
    new_table, expand=False, box=box.SIMPLE_HEAD, border_style="cyan"
)


@flexitable.register
@cache
@debug
def _any_tuple(data: tuple[Any, ...]) -> RenderableType:
    return _handle_mixed_list_items(data)


@flexitable.register
@cache
@debug
def _str_list(data: tuple[str, ...]) -> RenderableType:
    return format_with_color(data)


@flexitable.register
@cache
@debug
def _int_list(data: tuple[int, ...]) -> Columns:
    return Columns(str(x) for x in data)


def _handle_mixed_list_items(data: tuple[Any, ...]) -> RenderableType:
    """Handle a list containing mixed item types."""
    return list_table(
        [flexitable(d) for d in data],
        show_lines=True,
        border_style="dim",
        show_edge=True,
        box=box.DOUBLE,
    )


def get_item_list_table(items: list[HashableDict], keys: Iterable[str]) -> Table:
    """Add rows for normal sized dictionary items as a sub-table."""
    table = simple_head_table(*keys, show_header=True)
    for item in items:
        table.add_dict_row(item, ignore_extra_fields=True, transform=flexitable)

    for column in table.columns:
        column.header_style = predictably_random_color(str(column.header))

    return table


def _render_dict_list(data: tuple[HashableDict, ...]) -> RenderableType:
    """Render a list of dictionaries with consistent structure handling."""
    if count_key := next((k for k in data[0] if MATCH_COUNT_HEADER.search(k)), None):
        data = add_count_bars(data, count_key)

    keys = dict.fromkeys(k for k in data[0] if any(i.get(k) for i in data)).keys()
    get_values = itemgetter(*keys)

    data_by_size: dict[bool, list[HashableDict]] = defaultdict(list)
    for item in [dict(zip(keys, get_values(i))) for i in data]:
        too_big = len(str(item.values())) > MAX_DICT_LENGTH
        data_by_size[too_big].append(item)

    table = new_table()
    if small_items := data_by_size[False]:
        table.add_row(get_item_list_table(small_items, keys))

    if large_items := data_by_size[True]:
        for idx, item in enumerate(large_items):
            data = flexitable(item)
            data.hide_root = True
            table.add_row(str(idx), border_panel(data))

    return table


@flexitable.register
@cache
@debug
def _dict_list(data: tuple[HashableDict, ...]) -> RenderableType:
    """Render a list of dictionaries as a rich table or tree structure.

    Processes collections of dictionaries, adapting the presentation format based on:
    - Data content (empty vs non-empty)
    - Dictionary size (large vs small)
    - Structure consistency (common keys)
    - Presence of numeric count fields

    For large dictionaries (exceeding MAX_DICT_LENGTH), items are rendered as trees
    with expandable nodes. For smaller dictionaries, items are combined into tabular
    format with columns for each key. Special handling is applied for count fields
    which are rendered as visualization bars when present.

    When dictionaries have inconsistent structures, appropriate formatting decisions
    are made to ensure readability, including grouping similar structures together.
    """
    data = tuple(filter(None, data))
    if not data:
        return ""

    if not all(isinstance(d, HashableDict) for d in data):
        return _handle_mixed_list_items(data)

    data = tuple(prepare_dict(item) for item in data)
    return _render_dict_list(data)
