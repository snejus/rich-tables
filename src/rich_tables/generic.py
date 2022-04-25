import itertools as it
from collections import ChainMap
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Set, Type, Union

from rich import box
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
    new_table,
    new_tree,
    wrap
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


@flexitable.register(dict)
def _dict(data: Dict, header: str = ""):
    table = new_table(
        "", "", show_header=False, border_style="misty_rose1", box=box.MINIMAL
    )
    table.columns[0].style = "bold misty_rose1"

    rends: List[ConsoleRenderable] = []
    for key, content in data.items():
        # table.add_row(flexitable(key), flexitable(content))
        # add_to_table(rends, table, content, key)
        add_to_table(rends, table, flexitable(content, key), key)

    rends = [table, *rends]

    if not header:
        return border_panel(Group(*rends), title=header or key)
    return new_tree(rends, title=header or key)


@flexitable.register(list)
def _list(data: List[Any], header: str = ""):
    def only(data_list: Iterable[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    if len(data) == 1:
        return flexitable(data[0], "hio")

    table = new_table(show_header=True)
    common_table = new_table(show_header=True)
    if only(data, str):
        # ["hello", "hi", "bye", ...]
        return " ".join(map(format_with_color, data))

    if only(data, dict):
        # [{"hello": 1, "hi": true}, {"hello": 100, "hi": true}]
        first_item = data[0]
        keys: Set[str] = set.union(*map(lambda x: set(x.keys()), data))
        vals_types = set(map(type, first_item.values()))
        if (
            len(keys) == 2
            and len(vals_types.intersection({int, float, str})) == 2
            or "count" in keys
        ):
            # [{"some_count": 10, "some_entity": "entity"}, ...]
            return counts_table(data)

        headers = []
        key_uniq_vals = zip(
            keys, map(lambda x: set(map(str, map(lambda y: y.get(x) or "", data))), keys)
        )
        for col, values in sorted(
            key_uniq_vals, key=lambda x: (len(x[1]), len("".join(x[1])))
        ):
            if len(data) > 1 and len(values) == 1:
                common_table.add_row(wrap(col, "b"), *values)
            else:
                table.add_column(col)

        # aux_table = new_table(*headers, show_header=False)
        for item in data:
            # for col, value in item.items():
            # add_to_table([], table, flexitable(item, header), header)
            table.take_dict_item(item, transform=flexitable)
    else:
        for item in data:
            table.add_row(*flexitable(item, header))
            # add_to_table(, table, flexitable(item, header), header)

    return border_panel(
        (Group(common_table, table) if common_table.row_count else table), title=header
    )
