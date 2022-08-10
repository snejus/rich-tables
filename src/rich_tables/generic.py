import itertools as it
import operator as op
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Type, Union

from ordered_set import OrderedSet as ordset  # type: ignore[import]
from rich import box
from rich.console import ConsoleRenderable
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
        # rends.append(content)
        if getattr(content, "title", None) and not content.title:
            content.title = key
        rends.append(content)
    else:
        if key:
            args.append(key)
        # if isinstance(content, Iterable) and not isinstance(content, str):
        #     args.append(content)
        # def static class method else:
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
        expand=False,
    )
    table.columns[0].style = "bold misty_rose1"

    rends: List[ConsoleRenderable] = []
    for key, content in data.items():
        add_to_table(rends, table, flexitable(content, key), key)

    # for rend in rends:
    #     table.add_row(rend)
    # rends = [table, *rends]

    # lines: List[List[ConsoleRenderable]] = []
    # line_width = 0
    # for rend in rends:
    #     width = console.measure(rend).maximum
    #     if line_width + width < console.width:
    #         if not lines:
    #             lines.append([rend])
    #         else:
    #             lines[-1].append(rend)
    #         line_width += width
    #     else:
    #         line_width = width
    #         lines.append([rend])

    # rend_lines: List[ConsoleRenderable] = []
    # for line in lines:
    #     if len(line) == 1:
    #         rend_lines.append(line[0])
    #     else:
    #         rend_lines.append(
    #             new_table(
    #                 rows=[map(lambda x: Align.left(x, vertical="middle"), line)],
    #                 expand=True,
    #                 justify="left",
    #             )
    #         )

    if rends:
        # rend_table = new_table("", rows=[[rend] for rend in rends])
        # return border_panel(Group(table, rend_table), title=header)
        return new_tree([table, *rends], title=header)
    else:
        return border_panel(table, title=header)

    # if header:
    #     return new_tree(rend_lines, title=header)
    # else:
    #     return rend_lines
    # return Group(*rend_lines)
    # return new_tree(rend_lines, title=header or key)


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
        all_keys = ordset(it.chain(*(tuple(d.keys()) for d in data)))
        if {"before", "after"}.issubset(all_keys):
            all_keys.add("diff")
            for idx in range(len(data)):
                item = data[idx]
                before, after = item.pop("before", None), item.pop("after", None)
                if isinstance(before, list):
                    before, after = "\n".join(before), "\n".join(after)

                if isinstance(before, str):
                    item["diff"] = make_difftext(before, after, "\n ")
                else:
                    keys = before.keys()
                    data[idx] = {
                        k: make_difftext(before[k] or "", after[k] or "") for k in keys
                    }

        keys = ordset(filter(lambda k: any((d.get(k) for d in data)), all_keys))
        vals_types = set(map(type, data[0].values()))
        if (
            (
                len(keys) in {2, 3}
                and len(vals_types.intersection({int, float, str})) == 2
            )
            or len(keys) < 8
            and any(map(lambda x: x in " ".join(keys), ("count_", "sum_", "duration")))
        ):
            return counts_table(data, header=header)

        if 1 < len(keys) < 15:
            for col in keys:
                table.add_column(col)

            for item in data:
                table.add_dict_item(item, transform=flexitable)
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
        table.header_style = "on grey3"
        for col in table.columns:
            if col.header:
                new_header = DISPLAY_HEADER.get(col.header) or col.header
                col.header = wrap(
                    new_header, f"b {predictably_random_color(new_header)}"
                )

    if header:
        table.show_header = False
        return border_panel(table, title=header, padding=1, border_style=f"dim {color}")
    else:
        return simple_panel(table)
