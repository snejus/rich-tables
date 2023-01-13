import itertools as it
import json
import logging
import os
import re
from datetime import datetime
from functools import partial
from typing import Any, Dict, Iterable, List, Optional, Union

from multimethod import multimethod
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, RenderableType
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from .utils import (
    DISPLAY_HEADER,
    FIELDS_MAP,
    NewTable,
    border_panel,
    counts_table,
    format_with_color,
    make_console,
    make_difftext,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    wrap,
)

JSONDict = Dict[str, Any]
console = make_console()


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


def debug(func, data):
    if log.isEnabledFor(10):
        log.debug(func.__annotations__["data"])
        console.log(data)


def mapping_view_table(**kwargs: Any) -> NewTable:
    """A table with two columns
    * First for bold field names
    * Second one for values
    """
    table = new_table(border_style="misty_rose1", box=box.MINIMAL, expand=False)
    table.add_column(justify="right", style="bold misty_rose1")
    table.add_column()
    return table


def prepare_dict(item: JSONDict) -> JSONDict:
    if "before" in item and "after" in item:
        before, after = item.pop("before"), item.pop("after")
        if not item.get("diff"):
            if isinstance(before, list):
                before, after = "\n".join(before), "\n".join(after)

            if isinstance(before, str):
                item["diff"] = make_difftext(before, after)
            else:
                keys = before.keys()
                item["diff"] = json.dumps(
                    {
                        k: make_difftext(str(before[k] or ""), str(after[k] or ""))
                        for k in keys
                    },
                    indent=2,
                )
    return item


@multimethod
def flexitable(data, header="") -> RenderableType:
    debug(_, data)
    return str(data)


@flexitable.register
def _(data: str) -> RenderableType:
    debug(_, data)
    if "[/]" not in data:
        data = data.replace("[", "⟦").replace("]", "⟧")
    return " | ".join(map(format_with_color, data.split(" | ")))


@flexitable.register
def _(data: str, header: str) -> RenderableType:
    debug(_, data)
    if "[/]" not in data:
        data = data.replace("[", "⟦").replace("]", "⟧")
    return FIELDS_MAP[header](data)


@flexitable.register
def _(data: Union[int, float], header: Optional[str] = "") -> RenderableType:
    debug(_, data)
    return flexitable(str(data), header)


@flexitable.register
def _(data: JSONDict, header: Optional[str] = "") -> RenderableType:
    debug(_, data)
    data = prepare_dict(data)
    table = mapping_view_table()
    cols: List[RenderableType] = []
    for key, content in data.items():
        if not content:
            continue

        content = flexitable(content, key)
        if isinstance(content, ConsoleRenderable) and not isinstance(content, Markdown):
            cols.append(border_panel(content, title=flexitable(key)))
        else:
            table.add_row(key, content)

    cols.insert(0, table)
    if header:
        return Columns(cols)

    table = new_table()
    row: List[RenderableType]
    row, width = [], 0
    rows: List[Panel] = []
    for rend in cols:
        this_width = console.measure(rend).maximum
        if width + this_width > console.width:
            rows.append(simple_panel(new_table(rows=[row], padding=(0, 0))))
            row, width = [rend], this_width
        else:
            row.append(rend)
            width += this_width
    rows.append(simple_panel(new_table(rows=[row], padding=(0, 0))))
    table.add_rows([[r] for r in rows])
    return table


list_table = partial(new_table, expand=False, box=box.SIMPLE_HEAD, border_style="cyan")


@flexitable.register
def _(data: List[str], header: str = "") -> RenderableType:
    debug(_, data)
    call = FIELDS_MAP.get(header)
    return (
        call("\n".join(data))
        if call and call != str
        else "\n".join(map(format_with_color, map(str, data)))
    )


@flexitable.register
def _(data: List[int], header: Optional[str] = None) -> RenderableType:
    debug(_, data)
    return border_panel(Columns(str(x) for x in data))


@flexitable.register
def _(data: List[JSONDict], header: Optional[str] = None) -> RenderableType:
    debug(_, data)
    data = [prepare_dict(item) for item in data if item]
    all_keys = dict.fromkeys(it.chain.from_iterable(tuple(d.keys()) for d in data))
    keys = {
        k: None for k in all_keys if any(((d.get(k) is not None) for d in data))
    }.keys()

    overlap = set(map(type, data[0].values())) & {int, float, str}
    get_match = re.compile(r"count_|(count$)|sum_|duration").search
    count_key = next(filter(None, map(get_match, keys)), None)
    if len(overlap) == 2 and count_key:
        return counts_table(data, count_key.string, header=header or "")

    def getval(value, key):
        trans = flexitable(value, key)
        if isinstance(trans, str):
            return f"{wrap(key, 'b')}: {trans}"
        if not trans:
            return str(trans)
        return trans

    large_table = list_table()
    for large, items in it.groupby(data, lambda i: len(str(i.values())) > 1200):
        if large:
            for item in items:
                values = (
                    getval(*args)
                    for args in sorted(
                        [(v or "", k) for k, v in item.items() if k in keys],
                        key=lambda x: str(type(x[0])),
                        reverse=True,
                    )
                )
                large_table.add_row(border_panel(new_tree(values, "")))
        else:
            sub_table = list_table(show_header=True)
            for key in keys:
                sub_table.add_column(key, header_style=predictably_random_color(key))
            for item in items:
                sub_table.add_dict_item(item, transform=flexitable)
            for col in sub_table.columns:
                col.header = DISPLAY_HEADER.get(col.header, col.header)
            large_table.add_row(sub_table)
    return large_table


@flexitable.register
def _(data: List[Any], header: Optional[str] = None) -> ConsoleRenderable:
    if len(data) == 1:
        return flexitable(data[0])
    debug(_, data)
    table = list_table(show_header=False)
    for item in filter(None, data):
        content = flexitable(item)
        if isinstance(content, Iterable) and not isinstance(content, str):
            table.add_row(*content)
        else:
            table.add_row(content)

    return simple_panel(table)
