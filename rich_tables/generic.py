from __future__ import annotations

import itertools as it
import logging
import os
from datetime import datetime
from functools import partial, wraps
from itertools import groupby
from typing import Any, Callable, Dict, Generator, List, Sequence, TypeVar, Union

import snoop
from multimethod import multidispatch
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group, RenderableType
from rich.logging import RichHandler

snoop.install(color=True)
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from . import fields
from .fields import DISPLAY_HEADER, MATCH_COUNT_HEADER, _get_val, add_count_bars
from .utils import (
    NewTable,
    border_panel,
    format_with_color,
    make_console,
    new_table,
    new_tree,
    predictably_random_color,
    wrap,
)

JSONDict = Dict[str, Any]
T = TypeVar("T")
console = make_console()

indent = ""

MAX_DICT_LENGTH = int(os.getenv("TABLE_MAX_DICT_LENGTH") or 500)
MAX_DICT_KEYS = int(os.getenv("TABLE_MAX_DICT_KEYS") or 10)


def time_fmt(current: datetime) -> Text:
    diff = current - time_fmt.prev  # type: ignore [attr-defined]
    time_fmt.prev = current  # type: ignore [attr-defined]
    return Text(f"{diff.total_seconds() * 100:.2f}s")


time_fmt.prev = datetime.now()  # type: ignore [attr-defined]


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


def _debug(_func: Callable[..., T], *args) -> None:
    if log.isEnabledFor(10):
        global indent
        data, *header = (str(arg).split(r"\n")[0] for arg in args)
        print(
            indent
            + " ".join([
                f"Function \033[1;31m{_func.__name__}\033[0m",
                f"Types: \033[1;33m{list(_func.__annotations__.values())[:-1]}\033[0m",
                f"Header: \033[1;35m{header[0]}\033[0m " if header else "",
                f"Data: \033[1m{data}\033[0m" if data else "",
            ])
        )

        indent += "│ "


def _undebug(_type: type, *args: Any) -> None:
    global indent
    indent = indent[:-2]
    if log.isEnabledFor(10):
        print(f"{indent}└─ " + f"Returning {_type}")


def mapping_view_table() -> NewTable:
    """Return a table with two columns.

    * First for bold field names
    * Second one for values.
    """
    table = new_table(border_style="cyan", style="cyan", box=box.MINIMAL, expand=False)
    table.add_column(justify="right", style="bold misty_rose1")
    table.add_column()
    return table


def prepare_dict(item: JSONDict) -> JSONDict:
    if "before" in item and "after" in item:
        item["diff"] = (item.pop("before"), item.pop("after"))
    return item


def debug(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any) -> T:
        _debug(func, *args)
        result = func(*args)
        _undebug(type(result), *args)
        return result

    return wrapper


@multidispatch
@debug
def flexitable(data) -> RenderableType:
    return str(data)


@flexitable.register
@debug
def _header(data: Any, header: str) -> RenderableType:
    if data in ("", [], {}):
        return ""

    if header.endswith(".py") and isinstance(data, str):
        return _get_val(data, header)

    if header not in fields.FIELDS_MAP or isinstance(data, list):
        return flexitable(data)

    out = _get_val(data, header)
    if not isinstance(out, str) and isinstance(out, type(data)):
        return flexitable(out)

    return out


@flexitable.register
@debug
def _tuple_header(data: tuple, header: str) -> RenderableType:  # type: ignore[type-arg]
    return fields.FIELDS_MAP[header](data) if header in fields.FIELDS_MAP else str(data)


@flexitable.register
@debug
def _renderable(data: Union[ConsoleRenderable, NewTable]) -> RenderableType:
    return data


@flexitable.register
@debug
def _str(data: str) -> RenderableType:
    return data


@flexitable.register
@debug
def _json_dict(data: JSONDict) -> RenderableType:
    data = prepare_dict(data)
    table = mapping_view_table()
    cols: List[RenderableType] = []
    for key, content in data.items():
        if content is None or (isinstance(content, list) and not content):
            continue

        value = flexitable(content, key)
        if isinstance(value, Generator):
            cols.append(border_panel(Group(*value), title=key))
        elif isinstance(value, (NewTable, Text, dict, Columns)):
            cols.append(border_panel(value, title=key))
        elif isinstance(value, ConsoleRenderable) and hasattr(value, "title"):
            value.title = key
            cols.append(value)
        elif isinstance(value, ConsoleRenderable) and not isinstance(value, Markdown):
            cols.append(value)
        else:
            table.add_row(key, value)

    if table.rows:
        cols.insert(0, table)

    yield from cols

    # return border_panel(Group(*cols))
    # yield from cols

    # row: List[RenderableType] = []
    # width = 0
    # rows: List[RenderableType] = []
    # for rend in cols:
    #     this_width = console.measure(rend).maximum
    #     if width + this_width > console.width:
    #         rows.append(Columns(row, equal=True, padding=(0, 0)))
    #         row, width = [rend], this_width
    #     else:
    #         row.append(rend)
    #         width += this_width

    # rows.append(Columns(row, equal=True, padding=(0, 0)))

    # return list_table(rows, padding=(0, 0))


simple_head_table = partial(
    new_table, expand=False, box=box.SIMPLE_HEAD, border_style="cyan"
)


@flexitable.register
@debug
def _list(data: list) -> RenderableType:
    return flexitable(tuple(data))


@flexitable.register
@debug
def _str_list(data: Sequence[str]) -> RenderableType:
    return format_with_color(data)


@flexitable.register
@debug
def _int_list(data: Sequence[int]) -> Columns:
    return Columns(str(x) for x in data)


@flexitable.register
@debug
def _dict_list(data: Sequence[JSONDict]) -> RenderableType:
    data = list(filter(None, data))
    if not data:
        return None

    data = [prepare_dict(item) for item in data if item]
    all_keys = dict.fromkeys(it.chain.from_iterable(tuple(d.keys()) for d in data))
    if not all_keys:
        return simple_head_table([])

    keys = {
        k: None for k in all_keys if any((d.get(k) is not None) for d in data)
    }.keys()

    overlap = set(map(type, data[0].values())) & {int, float, str}

    if overlap and any(MATCH_COUNT_HEADER.search(k) for k in keys):
        data = add_count_bars(data)
        keys = data[0].keys()

    def getval(value: Any, key: str) -> RenderableType:
        transformed_value = flexitable(value, key)
        header = wrap(key, "b")
        if (
            isinstance(transformed_value, NewTable)
            and len(transformed_value.rows) == 1
            and len(transformed_value.columns) == 1
        ):
            transformed_value = transformed_value.columns[0]._cells[0]

        if isinstance(transformed_value, str):
            return f"{header}: {transformed_value}"

        if isinstance(transformed_value, (Panel, NewTable)):
            transformed_value = new_tree([transformed_value], header)
        elif isinstance(transformed_value, Tree):
            transformed_value.label = header

        elif isinstance(transformed_value, Generator):
            return Group(*transformed_value, fit=False)

        return transformed_value

    large_table = simple_head_table()
    for large, items in groupby(data, lambda i: len(str(i.values())) > MAX_DICT_LENGTH):
        items = list(items)
        if large:
            for item in items:
                values = it.starmap(
                    getval,
                    sorted(
                        [(v or "", k) for k, v in item.items() if k in keys],
                        key=lambda x, *_: str(type(x)),
                        reverse=True,
                    ),
                )
                tree = new_tree(values, "")
                large_table.add_row(tree)
        else:
            sub_table = simple_head_table(show_header=True)
            for key in keys:
                sub_table.add_column(key, header_style=predictably_random_color(key))
            for item in items:
                sub_table.add_row(*[
                    (Group(*res) if isinstance(res, Generator) else res)
                    for k in keys
                    if (res := flexitable(item.get(k, ""), k)) is not None
                ])
            for col in sub_table.columns:
                col.header = DISPLAY_HEADER.get(str(col.header), col.header)
            large_table.add_row(sub_table)

    return large_table
