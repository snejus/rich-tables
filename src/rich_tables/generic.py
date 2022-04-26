import itertools as it
import operator as op
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Set, Type, Union

from ordered_set import OrderedSet
from rich import box, print
from rich.align import Align
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group
from rich.errors import NotRenderableError
from rich.layout import Layout
from rich.table import Table

from .utils import (
    FIELDS_MAP,
    border_panel,
    counts_table,
    format_with_color,
    new_table,
    new_tree,
    predictably_random_color,
    wrap,
    make_console,
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
    # if isinstance(content, Group):
    #     # if not content._renderables[0].title:
    #     print(len(content._renderables))
    #     content = border_panel(content)
    #         # content._renderables[0].title = key
    # if isinstance(content, Tree):
    #     rends.append(content)
    #     # table.add_row(key, content)
    # elif isinstance(content, Table):
    #     rends.append(content)
    # elif isinstance(content, Panel):
    #     content.expand = False
    #     content.title_align = "left"
    #     content.title = wrap(key[:65], "b")
    #     if hasattr(content, "renderable") and isinstance(content.renderable, Table):
    #         content.renderable.show_header = False
    #         content.renderable.expand = False
    #     rends.append(content)
    # else:
    args = []
    if isinstance(content, ConsoleRenderable):
        rends.append(content)
    else:
        if key:
            args.append(key)
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
        "", "", show_header=False, border_style="misty_rose1", box=box.MINIMAL, expand=False
    )
    table.columns[0].style = "bold misty_rose1"

    rends: List[ConsoleRenderable] = []
    for key, content in data.items():
        # table.add_row(flexitable(key), flexitable(content))
        # add_to_table(rends, table, content, key)
        add_to_table(rends, table, flexitable(content, key), key)

    rends = [table, *rends]

    for rend in rends:
        print(console.measure(rend))
        print(console.width)
    if not header:
        return Group(*rends)
    return new_tree(rends, title=header or key)


@flexitable.register(list)
def _list(data: List[Any], header: str = ""):
    def only(data_list: Iterable[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    if only(data, str):
        # ["hello", "hi", "bye", ...]
        return " ".join(map(format_with_color, data))

    if len(data) == 1:
        return flexitable(data[0], header)

    table = new_table(show_header=True)

    if only(data, dict):
        # [{"hello": 1, "hi": true}, {"hello": 100, "hi": true}]
        first_item = data[0]
        keys = OrderedSet.union(*map(lambda x: OrderedSet(x.keys()), data))
        vals_types = set(map(type, first_item.values()))
        if (
            len(keys) == 2
            and len(vals_types.intersection({int, float, str})) == 2
            or "count" in keys
        ):
            # [{"some_count": 10, "some_entity": "entity"}, ...]
            return counts_table(data)

        color = predictably_random_color(str(keys))
        col_vals = zip(keys, map(lambda x: list(map(op.itemgetter(x), data)), keys))
        for col, values in col_vals:
            table.add_column(col)

        for item in data:
            table.take_dict_item(item, transform=flexitable)
    else:
        for item in data:
            table.add_row(*flexitable(item, header))

    table.expand = False
    # table.collapse_padding = True
    table.box = None
    color = predictably_random_color(header)
    for col in table.columns:
        col.header = wrap(f" {col.header} ", f"i b {color} on grey7")

    if header:
        table.show_header = False
        return border_panel(table, padding=1, box=box.ROUNDED, title=wrap(header, "b"), border_style="dim " + color, expand=False)
    return table
