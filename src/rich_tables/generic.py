import itertools as it
import operator as op
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Type, Union

from ordered_set import OrderedSet as ordset
from rich import box
from rich.columns import Columns
from rich.console import ConsoleRenderable, Group
from rich.errors import NotRenderableError
from rich.table import Table

from .utils import (DISPLAY_HEADER, FIELDS_MAP, border_panel, counts_table,
                    format_with_color, make_console, make_difftext, new_table,
                    new_tree, predictably_random_color, simple_panel, wrap)

JSONDict = Dict[str, Any]

console = make_console()


def add_to_table(
    rends: List[ConsoleRenderable], table: Table, content: Any, key: str = ""
):
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
        "",
        "",
        show_header=False,
        border_style="misty_rose1",
        box=box.MINIMAL,
        expand=True,
    )
    table.columns[0].style = "bold misty_rose1"

    rends: List[ConsoleRenderable] = []
    for key, content in data.items():
        add_to_table(rends, table, flexitable(content, key), key)

    if rends:
        # rend_table = new_table("", rows=[[rend] for rend in rends])
        # return border_panel(Group(table, rend_table), title=header)

        # table.add_rows([["", simple_panel(r)] for r in rends])
        # return new_tree([table], title=header)
        # print(header)
        # return new_tree([table, *rends], title=header)
        return new_tree([table, *rends])
    else:
        # return new_tree([table, *rends], title=header)
        # return border_panel(table, title=header)
        return border_panel(table)


@flexitable.register(list)
def _list(data: List[Any], header: str = ""):
    if not data:
        return None

    def only(data_list: Iterable[Any], _type: Type) -> bool:
        return all(map(lambda x: isinstance(x, _type), data_list))

    if only(data, str):
        """["hello", "hi", "bye", ...]"""
        return " ".join(map(format_with_color, data))

    if only(data, int):
        """[1, 2, 3, ...]"""
        return border_panel(Columns(str(x) for x in data))

    table = new_table(
        show_header=True, expand=False, box=box.SIMPLE_HEAD, border_style="cyan"
    )

    if only(data, dict):
        # [{"hello": 1, "hi": true}, {"hello": 100, "hi": true}]
        data: List[Dict]
        all_keys = ordset(it.chain(*(tuple(d.keys()) for d in data)))
        if {"before", "after"}.issubset(all_keys):
            all_keys.add("diff")
            for idx in range(len(data)):
                item = data[idx]
                before, after = item.pop("before", None), item.pop("after", None)
                if isinstance(before, list):
                    before, after = "\n".join(before), "\n".join(after)

                if isinstance(before, str):
                    item["diff"] = make_difftext(before, after)
                else:
                    keys = before.keys()
                    data[idx] = {
                        k: make_difftext(before[k] or "", after[k] or "") for k in keys
                    }

        keys = ordset(filter(lambda k: any((d.get(k) for d in data)), all_keys))
        if not keys:
            return None
        vals_types = set(map(type, data[0].values()))

        if (
            len(keys) in {2, 3} and len(vals_types.intersection({int, float, str})) == 2
        ) or (
            len(keys) < 8
            and all(x in " ".join(keys) for x in ["count_", "sum_", "duration"])
        ):
            return counts_table(data, header=header)
        # if (
        #     len(keys) in {2, 3} and len(vals_types.intersection({str, int, float})) == 2
        # ) or (
        #     len(keys) < 8
        #     and all(x in " ".join(keys) for x in ["count_", "sum_", "duration"])
        # ):
        #     return counts_table(data, header=header)

        if 1 < len(keys) < 15:
            for col in keys:
                table.add_column(col)
            # for item in data:
            #     tree.add(str(item.keys()))

            # if "items" not in data[0]:
            for item in data:
                table.add_dict_item(item, transform=flexitable)
            # else:
            #     tree = new_tree()
            #     for item in data:
            #         ntable = new_table()
            #         for col in keys:
            #             ntable.add_column(col)
            #         ntable.add_dict_item(item, transform=flexitable)
            #         items = item.pop("items", [])
            #         tree.add(flexitable([item]))
            #         if items and items[0]["subtask_key"] is not None:
            #             tree.add(border_panel(flexitable(items)))
            #     table.add_row(tree)
        else:
            table.show_header = False
            # for col in keys:
            #     table.add_column(col)
            for item in data:
                table.add_row(
                    flexitable(dict(zip(keys, map(lambda x: item.get(x, ""), keys))))
                )
                table.add_row("")
    else:
        for item in filter(op.truth, data):
            content = flexitable(item)
            if isinstance(content, Iterable) and not isinstance(content, str):
                table.add_row(*content)
            else:
                table.add_row(flexitable(item))

    color = predictably_random_color(header)
    if table.show_header:
        # table.header_style = "on grey3"
        # table.expand = True
        for col in table.columns:
            if col.header:
                new_header = DISPLAY_HEADER.get(col.header) or col.header
                col.header = wrap(new_header, f"{predictably_random_color(new_header)}")

    table.show_header = False
    if header:
        # table.show_header = False
        # table.expand = True
        # return table
        # return border_panel(table, title=header, border_style=f"dim {color}")
        # table.header = header
        return table
        # return simple_panel(table, expand=True, border_style=f"dim {color}")
    else:
        return table
