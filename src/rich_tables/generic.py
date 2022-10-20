import itertools as it
import operator as op
from functools import partial
from typing import Any, Dict, Iterable, List, Optional, Union

from multimethod import multimethod
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable
from rich.table import Table
from rich.text import Text

from .utils import (
    DISPLAY_HEADER,
    FIELDS_MAP,
    border_panel,
    counts_table,
    format_with_color,
    make_difftext,
    new_table,
    predictably_random_color,
    wrap,
)

JSONDict = Dict[str, Any]


def add_to_table(
    rends: List[ConsoleRenderable], table: Table, content: Any, key: str = ""
) -> None:
    args = []
    if isinstance(content, ConsoleRenderable):
        # if getattr(content, "title", None) and not content.title:
        # content.title = key
        # rends.append(content)
        table.add_row(key, content)
    else:
        if key:
            args.append(key)
        if isinstance(content, Iterable) and not isinstance(content, str):
            args.extend(content)
        else:
            args.append(content)
        table.add_row(*args)


@multimethod
def flexitable(data: None, header: str = "") -> str:
    return str(data)


@flexitable.register
def _(data: str, header: str = "") -> ConsoleRenderable:
    return FIELDS_MAP[header](data)


@flexitable.register
def _(data: Union[int, float], header: str = "") -> str:
    return flexitable(str(data), header)


@flexitable.register
def _(data: dict, header: Optional[str] = "") -> ConsoleRenderable:
    table = new_table(
        "",
        "",
        show_header=False,
        border_style="misty_rose1",
        box=box.MINIMAL,
        expand=False,
    )
    table.columns[0].style = "bold misty_rose1"

    all_keys = set(data.keys())
    if "before" in all_keys and "after" in all_keys:
        return Text.from_markup(
            make_difftext(data["before"], data["after"], ".0123456789")
        )
        # all_keys.update(diff=None)
        # for idx in range(len(data)):
        #     item = data[idx]
        #     before, after = item.pop("before", None), item.pop("after", None)
        #     if isinstance(before, list):
        #         before, after = "\n".join(before), "\n".join(after)

        #     if isinstance(before, str):
        #         item["diff"] = make_difftext(before, after)
        #     else:
        #         keys = before.keys()
        #         data[idx] = {
        #             k: make_difftext(before[k] or "", after[k] or "") for k in keys
        #         }

    rends: List[ConsoleRenderable] = []
    for key, content in data.items():
        add_to_table(rends, table, flexitable(content, key), key)

    return border_panel(table, highlight=False)


list_table = partial(new_table, expand=False, box=box.SIMPLE_HEAD, border_style="cyan")


@flexitable.register
def _(data: List[str], header: Optional[str] = None) -> str:
    return " ".join(map(format_with_color, data))


@flexitable.register
def _(data: List[int], header: Optional[str] = None) -> ConsoleRenderable:
    return border_panel(Columns(str(x) for x in data))


@flexitable.register
def _(data: List[JSONDict], header: Optional[str] = None) -> ConsoleRenderable:
    all_keys = dict.fromkeys(it.chain.from_iterable(tuple(d.keys()) for d in data))
    keys = {k: None for k in all_keys if any((d.get(k) for d in data))}.keys()
    vals_types = set(map(type, data[0].values()))

    if (
        2 <= len(keys) <= 3 and len(vals_types.intersection({int, float, str})) == 2
    ) and (
        len(keys) < 8
        and any(x in " ".join(keys) for x in ["count_", "_count", "sum_", "duration"])
    ):
        return counts_table(data, header=header or "")

    if 1 < len(keys) < 15:
        table = list_table(show_header=True)
        for col in keys:
            table.add_column(col)
        for item in data:
            table.add_dict_item(item, transform=flexitable)
        for col in filter(op.truth, table.columns):
            new_header = DISPLAY_HEADER.get(col.header) or col.header
            col.header = wrap(new_header, f"{predictably_random_color(new_header)}")

    else:
        table = list_table(show_header=False)
        for item in data:
            table.add_row(flexitable(dict(zip(keys, map(lambda x: item.get(x), keys)))))
            table.add_row("")

    return table


@flexitable.register
def _(data: List[Any], main_header: Optional[str] = None) -> ConsoleRenderable:
    table = list_table(show_header=True)
    for item in filter(op.truth, data):
        content = flexitable(item)
        if isinstance(content, Iterable) and not isinstance(content, str):
            table.add_row(*content)
        else:
            table.add_row(flexitable(item))
    table = list_table(show_header=False)
    for d in data:
        table.add_row(border_panel(flexitable(d)))

    return table
