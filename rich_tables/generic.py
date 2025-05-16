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
import sys
from collections import defaultdict
from collections.abc import Iterable
from contextlib import nullcontext, suppress
from datetime import datetime, timezone
from functools import cache, reduce, wraps
from itertools import groupby
from operator import and_
from typing import TYPE_CHECKING, Any, Callable, TypeVar, Union

from multimethod import multidispatch
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, RenderableType
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from . import fields
from .fields import MATCH_COUNT_HEADER, _get_val, add_count_bars
from .utils import (
    HashableDict,
    HashableList,
    NewTable,
    border_panel,
    console,
    format_string,
    list_table,
    new_table,
    new_tree,
    predictably_random_color,
    to_hashable,
    wrap,
)

if TYPE_CHECKING:
    from rich.table import Column


R = TypeVar("R", bound=RenderableType)
T = TypeVar("T")

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

        import snoop

        snooper = snoop
    else:
        snooper = nullcontext


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
                        f"Data: \033[1m{data}\033[0m" if data else "",  # ]]]]]
                    ]
                ),
                file=sys.stderr,
            )
            self.indent += "│ "

    def undebug(self, _type: type) -> None:
        self.indent = self.indent[:-2]
        if log.isEnabledFor(10):
            print(f"{self.indent}└─ " + f"Returning {_type}", file=sys.stderr)


_debug_logger = DebugLogger()


def debug(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any) -> T:
        _debug_logger.debug(func, *args)
        result = func(*args)
        _debug_logger.undebug(type(result))
        return result

    return wrapper


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
@cache
@debug
def _rend(data: ConsoleRenderable) -> RenderableType:
    return data


@flexitable.register
@cache
@debug
def _num(data: Union[str, float]) -> RenderableType:
    return format_string(str(data))


@flexitable.register
@debug
def _list(data: list[Any]) -> RenderableType:
    return flexitable(to_hashable(data))


@flexitable.register
@debug
def _dict(data: dict[str, Any]) -> RenderableType:
    if (rend := flexitable(to_hashable(data))) and isinstance(rend, Tree):
        rend.hide_root = True
    return rend


@flexitable.register
@cache
@debug
def _header(data: Any, header: str) -> RenderableType:
    with snooper():
        if not data and isinstance(data, Iterable):
            return ""

        if isinstance(data, HashableDict):
            tree = _json_dict(data)
            tree.label = wrap(header, "b")
            return border_panel(tree)

        if header.endswith(".py") and isinstance(data, str):
            return _get_val(data, header)

        if header in fields.FIELDS_MAP:
            with suppress(AttributeError, TypeError):
                return _get_val(data, header)

        return flexitable(data)


@flexitable.register
@debug
def _json_dict_list(data: HashableDict[str, HashableList[HashableDict]]) -> Tree:
    """Transform a nested dictionary structure into a displayable Tree.

    Processes an input dictionary where keys map to lists of records (further
    dictionaries). Each list of records is converted into a table. Column
    widths are harmonized across conceptually related columns in different
    tables before the entire structure is unified into a single Tree.

    Example data:
        {
            "Group A": [
                {"name": "Item 1", "value": 100, "status": "active"},
                {"name": "Item 2", "value": 200, "status": "pending"}
            ],
            "Group B": [
                {"name": "Item 3", "value": 150, "status": "active"},
                {"name": "Item 4", "value": 300, "status": "inactive"}
            ]
        }

        This would produce a Tree where each group key ("Group A", "Group B")
        contains a formatted table of its records. The "name", "value", and "status"
        columns would have consistent widths across both tables to ensure visual alignment.
    """
    result = HashableDict({f: flexitable(v) for f, v in data.items()})
    columns_by_header: dict[str, list[Column]] = defaultdict(list)
    for root_table in result.values():
        if isinstance(root_table, NewTable):
            for cell in root_table.columns[0].cells:
                if isinstance(cell, NewTable):
                    for col in cell.cols.values():
                        columns_by_header[NewTable.get_display_header(col)].append(col)

    for header, cols in columns_by_header.items():
        col_ratio = max(
            console.measure(_c).minimum + 1
            for col in cols
            for _c in [header, *col.cells]
        )
        for col in cols:
            col.ratio = col_ratio

    return flexitable(result)


@flexitable.register
@debug
def _json_dict(data: HashableDict) -> Tree:
    data = prepare_dict(data)
    tree = new_tree()
    for key, value in data.items():
        renderable = flexitable(value, key)
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


@flexitable.register
@cache
@debug
def _str_list(data: HashableList[str]) -> RenderableType:
    if not data:
        return ""
    return " ".join(map(flexitable, data))


@flexitable.register
@cache
@debug
def _list_list(data: HashableList[HashableList]) -> Union[Panel, str]:
    if not data:
        return ""

    return border_panel(
        list_table(
            map(flexitable, data),
            box=box.HORIZONTALS,
            show_lines=True,
            pad_edge=True,
            border_style="dim cyan",
        ),
        border_style="dim cyan",
    )


@flexitable.register
@cache
@debug
def _int_list(data: HashableList[int]) -> RenderableType:
    if not data:
        return ""
    return Columns(str(x) for x in data)


def _handle_mixed_list_items(data: HashableList[Any]) -> NewTable:
    """Handle a list containing mixed item types."""
    return list_table(
        [flexitable(d) for d in data],
        show_lines=False,
        border_style="dim",
        show_edge=False,
        box=box.DOUBLE,
    )


def get_item_list_table(
    items: Iterable[HashableDict], keys: Iterable[str], **kwargs: Any
) -> NewTable:
    """Add rows for normal sized dictionary items as a sub-table."""
    kwargs.setdefault("show_header", True)
    kwargs.setdefault("border_style", "cyan")
    kwargs.setdefault("box", box.SIMPLE_HEAD)
    table = new_table(*keys, **kwargs)

    for item in items:
        table.add_dict_row(item, transform=flexitable)

    for column in table.columns:
        column.header_style = predictably_random_color(str(column.header))

    return table


def _render_dict_list(data: HashableList[HashableDict]) -> NewTable:
    """Render a list of dictionaries with consistent structure handling."""
    if count_key := next((k for k in data[0] if MATCH_COUNT_HEADER.search(k)), None):
        data = add_count_bars(data, count_key)

    all_fields: dict[str, None] = {}
    for item in data:
        all_fields.update(dict.fromkeys(item))

    fields = all_fields
    # fields = dict.fromkeys(
    #     k for k in all_fields if any((i.get(k) not in {"", None}) for i in data)
    # ).keys()
    not_null_data = [
        HashableDict({k: v for k, v in i.items() if k in fields}) for i in data
    ]

    table = new_table(expand=True)
    for large, items in groupby(
        not_null_data, lambda i: len(str(i.values())) > MAX_DICT_LENGTH
    ):
        if large:
            for item in items:
                rend = flexitable(item)
                if isinstance(rend, Tree):
                    rend.hide_root = True
                table.add_row(border_panel(rend, expand=True))
        else:
            table.add_row(get_item_list_table(items, fields, expand=True))

    return table


@flexitable.register
@cache
@debug
def _dict_list(data: HashableList[HashableDict]) -> Union[NewTable, str]:
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
    data = HashableList(filter(None, data))
    if not data:
        return ""

    if not all(isinstance(d, HashableDict) for d in data) or (
        # no shared keys
        not reduce(and_, (i.keys() for i in data))
    ):
        return _handle_mixed_list_items(data)

    data = HashableList(prepare_dict(item) for item in data)
    return _render_dict_list(data)
