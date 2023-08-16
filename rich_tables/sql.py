import re
from collections import defaultdict
from itertools import groupby
from typing import Any, Dict, List

import sqlparse
from rich.rule import Rule
from rich.syntax import Syntax

from . import utils

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
console = utils.make_console()


def fmt_ordering(column: str) -> str:
    return ORDER_BY_PARTS_PAT.sub(
        lambda r: (
            "[b red]🢃[/]"
            if r[3] == "DESC"
            else "[b green]🢁[/]"
            if r[3] == "ASC"
            else ""
        )
        + utils.format_with_color(r[1])
        + (f".{utils.colored_with_bg(r[2])}" if r[2] else ""),
        column,
    )


def fmt_joins(column: str) -> str:
    return re.sub(
        r"JOIN (.+)", lambda r: "JOIN " + utils.format_with_color(r[1]), column
    )


utils.FIELDS_MAP.update(
    tables=utils.colored_split,
    operation=utils.colored_split,
    joins=lambda x: "\n".join(map(fmt_joins, x.split(", "))),
    order_by=lambda x: " ".join(map(fmt_ordering, re.split(r",\s+", x))),
    sql=lambda x: utils.border_panel(
        Syntax(
            sqlparse.format(x.replace('"', ""), strip_comments=True, reindent=True),
            "sql",
            theme="gruvbox-dark",
            background_color="black",
            word_wrap=True,
        )
    ),
)


def parse_sql_query(sql: str, span: float) -> dict:
    sql = sql.replace('"', "")
    kwargs = {"strip_comments": True}
    kwargs["reindent" if REINDENT else "reindent_aligned"] = True
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


def report_sql_query(data: JSONDict) -> None:
    return utils.FIELDS_MAP["sql"](data)


def get_duplicates(queries: JSONDict) -> JSONDict:
    data = [{f: q[f] for f in ("operation", "tables", "joins")} for q in queries]
    table_groups = groupby(sorted(data, key=lambda q: q["tables"]))
    with_counts = [{**data, "count": len(list(it))} for data, it in table_groups]
    return sorted(
        filter(lambda q: q["count"] > 1, with_counts), key=lambda q: q["count"]
    )


def report_queries(queries: List[JSONDict]) -> None:
    queries = list(filter(lambda q: q.get("tables"), queries))
    if queries:
        # duplicates = get_duplicates(queries)
        for query in queries:
            span = float(query["span"])
            query["time"] = "{:>7.2f}".format(round(query["time"] + span, 2))
            query["span"] = utils.wrap(
                f"{span:>5.2f}",
                "green" if span < 1 else "yellow" if span < 10 else "red",
            )

        # if duplicates:

        #     console.print(
        #         Rule(utils.wrap("Duplicate queries", "bold"), style="dim cyan")
        #     )
        #     console.print(utils.simple_panel(duplicates, expand=True))


def sql_table(data: List[JSONDict]):
    return utils.list_table(
        (utils._get_val(item["sql"], "sql") for idx, item in enumerate(data))
    )
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
