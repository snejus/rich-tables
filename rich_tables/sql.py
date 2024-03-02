import re
from collections import defaultdict
from typing import Any, Dict

import sqlparse

from .utils import format_with_color, format_with_color_on_black

QUERY_PARTS = [
    re.compile(
        r"(?P<operation>(SELECT(?! COUNT)|(?<=SELECT )COUNT|UPDATE|INSERT INTO|(RELEASE )?SAVEPOINT))"
    ),
    re.compile(r"(UPDATE|FROM|INTO) (?P<tables>[\w_]+)"),
    re.compile(r"SELECT.*\ (?P<tables>[\w_]+)\.id"),
    re.compile(r"(?P<joins>(\b[A-Z ]+JOIN [\w_]+)*)"),
    re.compile(r"ORDER BY (?P<order_by>([a-z_.,\s]+|DESC|ASC)*)"),
]
ORDER_BY_PARTS_PAT = re.compile(r"([^. ]+)(?:(?:\.)([^ ]+))*(?:(?: )(ASC|DESC))")

REINDENT = False

JSONDict = Dict[str, Any]


def fmt_ordering(column: str) -> str:
    return ORDER_BY_PARTS_PAT.sub(
        lambda r: (
            "[b red]🢃[/]"
            if r[3] == "DESC"
            else "[b green]🢁[/]"
            if r[3] == "ASC"
            else ""
        )
        + format_with_color(r[1])
        + (f".{format_with_color_on_black(r[2])}" if r[2] else ""),
        column,
    )


def fmt_joins(column: str) -> str:
    return re.sub(r"JOIN (.+)", lambda r: "JOIN " + format_with_color(r[1]), column)


def parse_sql_query(sql: str, span: float) -> dict:
    sql = sql.replace('"', "")
    kwargs = {"strip_comments": True}
    # kwargs["reindent" if REINDENT else "reindent_aligned"] = True
    kwargs["reindent_aligned"] = False
    kwargs["reindent"] = True
    sql = sqlparse.format(sql, **kwargs)
    query = defaultdict(str, span=round(span, 2), sql=sql)
    query = {
        "span": round(span, 2),
        "operation": "",
        "tables": "",
        "joins": "",
        "order_by": "",
    }

    for pat in QUERY_PARTS:
        m = pat.search(sql)
        if m:
            query.update(
                {k: v.strip() for k, v in m.groupdict().items() if not query[k]}
            )

    return query


# def report_sql_query(data: JSONDict) -> None:
#     return FIELDS_MAP["sql"](data)


# parsed_data = [
#     parse_sql_query(item["sql"], item["exclusive_time"]) for item in data
# ]
# summary_table = utils.new_table("id", *parsed_data[0].keys())
# for idx, item in enumerate(parsed_data):
#     item = {"id": str(idx), **{k: utils._get_val(v, k) for k, v in item.items()}}
#     summary_table.add_dict_item(item)

# item["sql"] = report_sql_query(item["sql"])
# for col in new_table.get_columns():
#     pass
# return utils.simple_panel(utils.new_table(rows=[[sql_table], [summary_table]]))
