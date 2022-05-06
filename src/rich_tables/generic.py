import itertools as it
import operator as op
from functools import singledispatch
from typing import Any, Dict, Iterable, List, Type, Union

from ordered_set import OrderedSet as ordset  # type: ignore[import]
from rich import box, print
from rich.align import Align
from rich.console import ConsoleRenderable, Group
from rich.errors import NotRenderableError
from rich.layout import Layout
from rich.table import Table

from .utils import border_panel
from .utils import (
    DISPLAY_HEADER,
    FIELDS_MAP,
    duration2human,
    format_with_color,
    get_val,
    make_console,
    make_difftext,
    new_table,
    new_tree,
    predictably_random_color,
    progress_bar,
    simple_panel,
    wrap
)

JSONDict = Dict[str, Any]


def counts_table(data: List[JSONDict]) -> Table:
    keys = set(data[0])
    count_col_name = "count"
    if count_col_name not in keys:
        for key, val in data[0].items():
            if isinstance(val, (int, float)):
                count_col_name = key

    all_counts = list(map(float, map(lambda x: x.get(count_col_name) or 0, data)))
    if min(all_counts) > 1:
        all_counts = list(map(int, all_counts))
    max_count = max(all_counts)

    headers = [*(keys - {count_col_name}), count_col_name]
    table = new_table(*headers, overflow="fold", vertical="middle")
    for item, count_val in zip(data, all_counts):
        table.add_row(
            *map(flexitable, op.itemgetter(*headers)(item)), progress_bar(count_val, max_count)
        )
    if count_col_name in {"duration", "total_duration"}:
        table.caption = "Total " + duration2human(float(sum(all_counts)), 2)
        table.caption_justify = "left"
    return table


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
    print(header)
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
                    rows=[map(lambda x: Align.left(x, vertical="middle"), line)],
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
        keys = ordset(filter(lambda k: any(filter(op.itemgetter(k), data)), data[0]))
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
        vals_types = set(map(type, data[0].values()))
        if (
            len(keys) == 2 and len(vals_types.intersection({int, float, str})) == 2
        ) or "count_" in " ".join(keys):
            # [{"some_count": 10, "some_entity": "entity"}, ...]
            return counts_table(data)

        if len(keys) < 15:
            for col in keys:
                table.add_column(col)

            for item in data:
                table.add_dict_item(item, transform=flexitable)
        else:
            for item in data:
                table.add_row(*flexitable(dict(zip(keys, op.itemgetter(*keys)(item)))))
                table.add_row("")
    else:
        for item in filter(op.truth, data):
            content = flexitable(item, header)
            if isinstance(content, Iterable) and not isinstance(content, str):
                table.add_row(*content)
            else:
                table.add_row(flexitable(item, header))

    color = predictably_random_color(header)
    cols = table.columns.copy()
    for col in cols:
        if col.header:
            # header = DISPLAY_HEADER.get(col.header, col.header)
            col.header = wrap(f" {col.header} ", f"i b {color} on grey7")

    if header:
        table.show_header = False
        return border_panel(table, title=header, padding=1, border_style=f"dim {color}")
    else:
        return simple_panel(table)
