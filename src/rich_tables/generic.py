import itertools as it
from functools import partial
from typing import Any, Dict, List, Optional, Union

from multimethod import multimethod
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group, RenderableType
from rich.markdown import Markdown
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
    predictably_random_color,
    simple_panel,
    wrap,
)

JSONDict = Dict[str, Any]
console = make_console()


def mapping_view_table(**kwargs: Any) -> NewTable:
    """A table with two columns
    * First for bold field names
    * Second one for values
    """
    table = new_table(border_style="misty_rose1", box=box.MINIMAL, expand=False)
    table.add_column(justify="right", style="bold misty_rose1")
    table.add_column()
    return table


@multimethod
def flexitable(data: None, header: str = "") -> RenderableType:
    return str(data)


@flexitable.register
def _(data: str, header: str = "") -> RenderableType:
    return FIELDS_MAP[header](data)


@flexitable.register
def _(data: Union[int, float], header: str = "") -> RenderableType:
    return flexitable(str(data), header)


@flexitable.register
def _(data: JSONDict, header: Optional[str] = "") -> RenderableType:
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

    table = mapping_view_table()
    cols = []
    for key, content in data.items():
        if not content:
            continue

        content = flexitable(content, key)
        if isinstance(content, ConsoleRenderable) and not isinstance(content, Markdown):
            cols.append(border_panel(content, title=key))
            # table.add_row(key, border_panel(content))
        else:
            table.add_row(key, content)

    cols.insert(0, simple_panel(table))
    if header:
        return Columns(cols)

    cols.sort(key=lambda x: console.measure(x).maximum)
    # return new_table(rows=it.zip_longest(*(iter(cols),) * 1))
    table = new_table()
    row, width = [], 0
    for rend in cols:
        this_width = console.measure(rend).maximum
        if width + this_width > console.width:
            # lines.append(simple_panel(new_table(rows=[row], padding=(0, 0))))
            table.add_row(simple_panel(new_table(rows=[row], padding=(0, 0))))
            row, width = [rend], this_width
        else:
            row.append(rend)
            width += this_width
    table.add_row(simple_panel(new_table(rows=[row], padding=(0, 0))))

    # print(len(cols), len(lines))
    return table


list_table = partial(new_table, expand=False, box=box.SIMPLE_HEAD, border_style="cyan")


@flexitable.register
def _(data: List[str], header: Optional[str] = None) -> str:
    return " ".join(map(format_with_color, data))


@flexitable.register
def _(data: List[int], header: Optional[str] = None) -> RenderableType:
    return border_panel(Columns(str(x) for x in data))


@flexitable.register
def _(data: List[JSONDict], header: Optional[str] = None) -> RenderableType:
    all_keys = dict.fromkeys(it.chain.from_iterable(tuple(d.keys()) for d in data))
    keys = {k: None for k in all_keys if any((d.get(k) for d in data))}.keys()

    if len(keys) >= 15:
        table = list_table(show_header=False)
        for item in data:
            table.add_row(flexitable({k: v for k, v in item.items() if k in keys}))
            table.add_row("")
        return table

    overlap = set(map(type, data[0].values())) & {int, float, str}
    keysstr = " ".join(keys)
    counting = any(x in keysstr for x in ["count_", "_count", "sum_", "duration"])
    if len(overlap) == 2 and counting:
        return counts_table(data, header=header or "")

    if 1 < len(keys) < 15:
        table = list_table(show_header=True)
        for key in keys:
            table.add_column(key)
        for item in data:
            table.add_dict_item(item, transform=flexitable)
        for col, old in ((c, str(c.header)) for c in table.columns if c):
            new = DISPLAY_HEADER.get(old) or old
            col.header = wrap(new, f"{predictably_random_color(new)}")

    return table
