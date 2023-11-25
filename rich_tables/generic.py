import itertools as it
import logging
import os
from datetime import datetime
from functools import partial
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type, Union

# import snoop
from multimethod import multimethod
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, RenderableType
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .fields import DISPLAY_HEADER, FIELDS_MAP, MATCH_COUNT_HEADER, counts_table
from .utils import (
    NewTable,
    border_panel,
    format_with_color,
    make_console,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    wrap,
)

# snoop.install(color=True)

JSONDict = Dict[str, Any]
console = make_console()

global indent
indent = ""

MAX_DICT_SIZE = 500


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
        # log_time_format="%H:%M:%S.%f",
        show_time=True,
        log_time_format=time_fmt,
    )
    log.addHandler(handler)
    if os.getenv("DEBUG"):
        log.setLevel("DEBUG")


def debug(
    _func: Callable[..., Any], data: Any = None, header: Optional[str] = None
) -> None:
    global indent
    if log.isEnabledFor(10):
        types = f"\033[1;33m{list(_func.__annotations__.values())[:-1]}\033[0m"
        print(indent + f"Function \033[1;31m{_func.__name__}\033[0m, types: {types}")
        print(indent + f"Header: \033[1m{header}\033[0m, Data: \033[1m{data}\033[0m")

    indent += "│ "


def undebug(type: Type, data: Any) -> None:
    global indent
    indent = indent[:-2]
    if log.isEnabledFor(10):
        print(indent + "└─ " + f"Returning {type} for {data}")


def mapping_view_table() -> NewTable:
    """A table with two columns
    * First for bold field names
    * Second one for values
    """
    table = new_table(border_style="cyan", style="cyan", box=box.MINIMAL, expand=False)
    table.add_column(justify="right", style="bold misty_rose1")
    table.add_column()
    return table


def prepare_dict(item: JSONDict) -> JSONDict:
    if "before" in item and "after" in item:
        item["diff"] = (item.pop("before"), item.pop("after"))
    return item


@multimethod
def flexitable(data: Any, header: str) -> RenderableType:
    debug(flexitable, data)
    value = str(data)
    undebug(type(value), data)
    return value


@flexitable.register
def _str(data: str) -> RenderableType:
    debug(_str, data)
    if "[/]" not in data:
        data = data.replace("[", "⟦").replace("]", "⟧")

    value = " | ".join(map(format_with_color, data.split(" | ")))
    undebug(type(value), data)
    return value


@flexitable.register
def _str_header(data: str, header: str) -> RenderableType:
    debug(_str_header, data)
    if "[/]" not in data:
        data = data.replace("[", "⟦").replace("]", "⟧")

    value = FIELDS_MAP[header](data)
    undebug(type(value), data)
    return value


@flexitable.register
def _int_or_float(data: Union[int, float], header: str) -> RenderableType:
    debug(_int_or_float, data)
    value = FIELDS_MAP[header](str(data))
    undebug(type(value), data)
    return value


@flexitable.register
def _tuple(data: Tuple[Any, ...], header: str) -> RenderableType:
    debug(_tuple, data)
    value = FIELDS_MAP[header](data)
    undebug(type(value), data)
    return value


@flexitable.register
def _json_dict(data: JSONDict, header: Optional[str] = None) -> RenderableType:
    debug(_json_dict, data, header)
    data = prepare_dict(data)
    table = mapping_view_table()
    cols: List[RenderableType] = []
    for key, content in data.items():
        if content is None or isinstance(content, list) and not content:
            continue

        content = flexitable(content, key)
        # reveal_type(content)
        if isinstance(content, ConsoleRenderable) and not isinstance(content, Markdown):
            cols.append(border_panel(content, title=flexitable(key)))
        else:
            table.add_row(key, content)

    cols.insert(0, table)
    # if header:
    #     return Columns(cols)

    table = new_table(padding=(0, 0))
    row: List[RenderableType]
    row, width = [], 0
    rows: List[RenderableType] = []
    for rend in cols:
        this_width = console.measure(rend).maximum
        if width + this_width > console.width:
            rows.append(Columns(row, equal=True, padding=(0, 0)))
            row, width = [rend], this_width
        else:
            row.append(rend)
            width += this_width

    rows.append(Columns(row, equal=True, padding=(0, 0)))
    table.add_rows([[r] for r in rows])

    value = table
    undebug(type(value), data)
    return table


list_table = partial(new_table, expand=False, box=box.SIMPLE_HEAD, border_style="cyan")


@flexitable.register
def _str_list(data: List[str], header: Optional[str] = None) -> RenderableType:
    debug(_str_list, data, header)
    call = FIELDS_MAP.get(str(header))
    value = (
        call("\n".join(data))
        if call and call != str
        else ", ".join(map(format_with_color, map(str, data)))
    )
    undebug(type(value), data)
    return value


@flexitable.register
def _int_list(data: List[int], header: Optional[str] = None) -> Panel:
    debug(_int_list, data)
    value = border_panel(Columns(str(x) for x in data))
    undebug(type(value), data)
    return value


@flexitable.register
def _dict_list(data: List[JSONDict], header: Optional[str] = None) -> Table:
    debug(_dict_list, data, header)
    if len(data) == 1 and len(data[0]) > 10:
        value = flexitable(data[0])
    else:
        data = [prepare_dict(item) for item in data if item]
        all_keys = dict.fromkeys(it.chain.from_iterable(tuple(d.keys()) for d in data))
        keys = {
            k: None for k in all_keys if any(((d.get(k) is not None) for d in data))
        }.keys()

        overlap = set(map(type, data[0].values())) & {int, float, str}

        if len(overlap) == 2 and any(MATCH_COUNT_HEADER.search(k) for k in keys):
            value = counts_table(data)
        elif "sql" in keys:
            from .sql import sql_table

            value = sql_table(data)
        else:

            def getval(value: Any, key: str) -> Iterable[RenderableType]:
                trans = flexitable(value, key)
                if isinstance(trans, str):
                    yield f"{wrap(key, 'b')}: {trans}"
                elif not trans:
                    yield str(trans)
                else:
                    yield f"{wrap(key, 'b')}:"
                    yield trans

            # large_table = list_table(title=header)
            large_table = list_table()
            for large, items in it.groupby(
                data, lambda i: len(str(i.values())) > MAX_DICT_SIZE
            ):
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
                        tree = new_tree(it.chain.from_iterable(values), "")
                        large_table.add_row(border_panel(tree))
                else:
                    sub_table = list_table(show_header=True)
                    for key in keys:
                        sub_table.add_column(
                            key, header_style=predictably_random_color(key)
                        )
                    for item in items:
                        sub_table.add_dict_item(item, transform=flexitable)
                    for col in sub_table.columns:
                        col.header = DISPLAY_HEADER.get(str(col.header), col.header)
                    large_table.add_row(sub_table)

                value = large_table

    undebug(type(value), data)
    return value


@flexitable.register
# def _any_list(data: List[Any], header: str) -> ConsoleRenderable:
# @snoop
def _any_list(data: List[Any], header: Optional[str] = None) -> RenderableType:
    if len(data) == 1:
        value = flexitable(data[0], header)
    else:
        debug(_any_list, data)
        table = list_table(show_header=False)
        for item in filter(None, data):
            content = flexitable(item)
            if isinstance(content, Iterable) and not isinstance(content, str):
                table.add_row(*content)
            else:
                table.add_row(content)

        value = simple_panel(table)
    undebug(type(value), data)
    return value
