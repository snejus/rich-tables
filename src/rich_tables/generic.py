import itertools as it
import operator as op
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Type, Union

from ordered_set import OrderedSet
from rich import box, print
from rich.align import Align
from rich.console import ConsoleRenderable, Group
from rich.errors import NotRenderableError
from rich.layout import Layout
from rich.table import Table

from .utils import (
    FIELDS_MAP,
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
    DISPLAY_HEADER
)

JSONDict = Dict[str, Any]


def make_bicolumn_layout(rends: List[ConsoleRenderable]) -> Layout:
    col_rows = dict(left=0, right=0)
    divided: Dict[str, List] = dict(left=[], right=[])
    standalone = []
    for rend in rends:
        rend.expand = False
        try:
            row_count = rend.renderable.row_count + 6
        except AttributeError:
            standalone.append(rend)
            continue
        else:
            side = "left" if col_rows["left"] <= col_rows["right"] else "right"
            divided[side].append(rend)
            col_rows[side] += row_count

    lay = Align.left(
        Group(
            *it.starmap(
                lambda r1, r2: Align.center(
                    new_table(
                        rows=[[Align.right(r1), Align.left(r2, vertical="middle")]]
                        if r2
                        else [[r1]]
                    )
                ),
                it.zip_longest(rends[::2], rends[1::2]),
            )
        )
    )
    return lay


def add_to_table(
    rends: List[ConsoleRenderable], table: Table, content: Any, key: str = ""
):
    args = []
    if isinstance(content, ConsoleRenderable):
        rends.append(content)
    else:
        if key:
            args.append(key)
        # if isinstance(content, Iterable) and not isinstance(content, str):
        #     args.append(content)
        # else:
        if isinstance(content, Iterable) and not isinstance(content, str):
            args.extend(content)
        else:
            args.append(content)
        table.add_row(*args)


@singledispatch
def flexitable(
    data: Union[JSONDict, List, ConsoleRenderable, str, int, float], header: str = ""
) -> Any:
    return data


@flexitable.register(str)
@flexitable.register(int)
def _str(data: Union[str, int], header: str = "") -> ConsoleRenderable:
    try:
        return FIELDS_MAP[header](data)
    except NotRenderableError:
        return FIELDS_MAP[header](str(data))


@flexitable.register
def _float(data: float, header: str = "") -> ConsoleRenderable:
    return FIELDS_MAP[header](str(data))


@flexitable.register
def _renderable(data: ConsoleRenderable, header: str = "") -> ConsoleRenderable:
    return data


console = make_console()


@flexitable.register(dict)
def _dict(data: Dict, header: str = ""):
    table = new_table(
        "",
        "",
        show_header=False,
        border_style="misty_rose1",
        box=box.MINIMAL,
        expand=False,
    )
    table.columns[0].style = "bold misty_rose1"

    rends: List[ConsoleRenderable] = []
    for key, content in data.items():
        add_to_table(rends, table, flexitable(content, key), key)

    rends = [table, *rends]

    lines: List[List[ConsoleRenderable]] = []
    line_width = 0
    for rend in rends:
        width = console.measure(rend).maximum
        if line_width + width < console.width:
            if not lines:
                lines.append([rend])
            else:
                lines[-1].append(rend)
            line_width += width
        else:
            line_width = width
            lines.append([rend])

    rend_lines: List[ConsoleRenderable] = []
    for line in lines:
        if len(line) == 1:
            rend_lines.append(line[0])
        else:
            rend_lines.append(
                new_table(
                    rows=[map(lambda x: Align.center(x, vertical="middle"), line)],
                    expand=True,
                    justify="left",
                )
            )

    if not header:
        return rend_lines
        # return Group(*rend_lines)
        # return new_tree(rend_lines, title=header or key)
    else:
        return new_tree(rend_lines, title=header or key)


@flexitable.register(list)
def _list(data: List[Any], header: str = ""):
    def only(data_list: Iterable[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    if only(data, str):
        # ["hello", "hi", "bye", ...]
        return " ".join(map(format_with_color, data))

    table = new_table(show_header=True, expand=False, box=None)

    if only(data, dict):
        # [{"hello": 1, "hi": true}, {"hello": 100, "hi": true}]
        first_item = data[0]
        keys = OrderedSet.union(*map(lambda x: OrderedSet(x.keys()), data))
        if {"before", "after"}.issubset(keys):
            for idx in range(len(data)):
                item = data[idx]
                keys = item["before"].keys()
                data[idx] = dict(
                    zip(
                        keys,
                        map(
                            lambda k: make_difftext(
                                item["before"][k] or "", item["after"][k] or ""
                            ),
                            keys,
                        ),
                    )
                )
        vals_types = set(map(type, first_item.values()))
        if (
            len(keys) == 2 and len(vals_types.intersection({int, float, str})) == 2
        ) or "count_" in " ".join(keys):
            # [{"some_count": 10, "some_entity": "entity"}, ...]
            return counts_table(data)

        for col in keys:
            if set(map(lambda x: str(x.get(col)), data)).issubset({None, ""}):
                continue
            table.add_column(col)

        for item in data:
            table.take_dict_item(item, transform=flexitable)
    else:
        for item in filter(op.truth, data):
            content = flexitable(item, header)
            if isinstance(content, Iterable) and not isinstance(content, str):
                table.add_row(*content)
            else:
                table.add_row(flexitable(item, header))

    color = predictably_random_color(header)
    cols = table.columns.copy()
    table.columns = []
    for col in cols:
        if col.header:
            header = DISPLAY_HEADER.get(col.header, col.header)
            col.header = wrap(f" {header} ", f"i b {color} on grey7")
        table.columns.append(col)

    if header:
        table.show_header = False
        return border_panel(table, title=header, padding=1, border_style=f"dim {color}")
    else:
        return simple_panel(table)
