import logging
import math
import re
import sys
import time
import typing as t
from collections import defaultdict
from itertools import groupby

import sqlparse
from django.db.backends.utils import CursorWrapper
from microservice import threadlocal
from rich.console import Console
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.syntax import Syntax
from rich_tables import utils
from rich_tables.generic import flexitable

logging.captureWarnings(False)
logger = logging.getLogger(__name__)


class CursorDebugWrapper(CursorWrapper):
    def execute(self, sql, params=None):
        start = time()
        try:
            return super(CursorDebugWrapper, self).execute(sql, params)
        finally:
            stop = time()
            duration = stop - start
            sql = self.db.ops.last_executed_query(self.cursor, sql, params)
            self.db.queries_log.append({"sql": sql, "time": "%.3f" % duration})
            logger.info(
                "%s___%.3f" % (sql, duration * 1000),
                extra={"duration": duration, "sql": sql, "params": params},
            )


utils.CursorDebugWrapper = CursorDebugWrapper
console = Console(force_interactive=1, force_terminal=1, color_system="256")

JSONDict = t.Dict[str, t.Any]

QUERY_PARTS = [
    re.compile(r"(?P<operation>(SELECT(?! COUNT)|(?<=SELECT )COUNT|UPDATE|^[A-Z ]+))"),
    re.compile(r"(?P<operation>^[A-Z ]+)"),
    re.compile(r"(UPDATE|FROM) (?P<tables>[\w_]+)"),
    re.compile(r"(?P<joins>[A-Z][A-Z ]+JOIN [\w_]+)"),
    re.compile(r"ORDER BY (?P<order_by>([a-z_.,\s]+|DESC|ASC)*)"),
]
ORDER_BY_PARTS_PAT = re.compile(r"([^. ]+)(?:(?:\.)([^ ]+))*(?:(?: )(ASC|DESC))")
REQUEST_TIMINGS_PAT = re.compile(r"(\d+) queries.* (\d+) ms SQL.* (\d+) ms total")


TESTING = "test" in sys.argv or any("pytest" in arg for arg in sys.argv)


def print_panel(data, title=None, style=None) -> None:
    if isinstance(data, (list, dict)):
        data = flexitable(data)
    console.print(Rule(utils.wrap(title, "bold"), style=style or "dim cyan"))
    console.print(utils.simple_panel(data, expand=True))


def report_durations(query_count: int, sql_time: int, request_time: int) -> None:
    if request_time and sql_time:
        ratio = round(request_time / sql_time, 1)
        if ratio < 20:
            color = f"#{int(ratio / 20 * 255):02X}FF00"
        else:
            color = f"#FF{int(255 - min(ratio, 100) / 100 * 255):02X}00"

        print_panel(
            utils.new_tree(
                [
                    utils.new_tree(
                        [ProgressBar(completed=sql_time / request_time * 100)],
                        title=f"SQL: {query_count} queries, {sql_time} ms",
                        guide_style="black",
                    ),
                    utils.new_tree(
                        [ProgressBar(completed=99.9, complete_style=color)],
                        title=(
                            f"Request: {request_time} ms. "
                            f"Python code took {round(request_time / (sql_time or 1), 1)} "
                            "times longer than the DB"
                        ),
                        guide_style="black",
                    ),
                ],
                hide_root=True,
            ),
            title="Summary",
        )


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
)


def get_duplicates(queries: JSONDict) -> JSONDict:
    data = [{f: q.get(f) for f in ("operation", "tables")} for q in queries]
    table_groups = groupby(sorted(data, key=lambda q: q["tables"]))
    with_counts = [{**data, "count": len(list(it))} for data, it in table_groups]
    return sorted(
        filter(lambda q: q["count"] > 1, with_counts), key=lambda q: q["count"]
    )


def get_spans(prev_end: float, curr_span: float, curr_end: float) -> t.Tuple[int, int]:
    curr_end = round(curr_end)
    curr_start = curr_end - math.ceil(curr_span)
    return curr_start - round(prev_end), curr_end - curr_start


def illustrate(queries: JSONDict) -> None:
    first = queries[0]
    consec_pairs = zip(queries, queries[1:])
    spans = [
        (
            *get_spans(0, first["span"], first["span"]),
            utils.predictably_random_color(first["tables"].split(", ")[0]),
        )
    ] + [
        (
            *get_spans(a["time"], b["span"], b["time"]),
            utils.predictably_random_color(b["tables"].split(", ")[0]),
        )
        for a, b in consec_pairs
    ]
    return "".join(
        "[dim red]─[/]" * py + utils.wrap("█" * sql, f"b {color}")
        for py, sql, color in spans
    )


def report_queries(queries: t.List[defaultdict]) -> None:
    queries = list(filter(lambda q: q.get("tables"), queries))
    if queries:
        duplicates = get_duplicates(queries)
        illustration = illustrate(queries)
        for query in queries:
            span = float(query["span"])
            query["time"] = "{:>7.2f}".format(round(query["time"] + span, 2))
            query["span"] = utils.wrap(
                f"{span:>5.2f}",
                "green" if span < 1 else "yellow" if span < 10 else "red",
            )

        fields = "time", "span", "operation", "tables", "joins", "order_by"
        print_panel(
            [{f: q.get(f) or "" for f in fields} for q in queries], title="Timeline"
        )
        print_panel(illustration, title="Timeline illustration")

        if duplicates:
            print_panel(duplicates, title="[red]Duplicate queries[/]", style="dim red")


def report_sql_query(data: JSONDict) -> None:
    console.print(
        Panel(
            Syntax(
                data["sql"],
                lexer="sql",
                theme="dracula",
                background_color="black",
                word_wrap=True,
            ),
            title=(f"[b]{data['span']} ms[/]" if data["span"] else ""),
            title_align="left",
            border_style="dim cyan",
        )
    )


def parse_sql_query(sql: str, span: float) -> dict:
    sql = sql.replace('"', "")
    kwargs = {"strip_comments": True}
    kwargs["reindent" if TESTING else "reindent_aligned"] = True
    sql = sqlparse.format(sql, **kwargs)
    query = defaultdict(str, span=round(span, 2), sql=sql)

    for pat in QUERY_PARTS:
        result = defaultdict(list)
        for m in pat.finditer(sql):
            for field, value in m.groupdict().items():
                result[field].append(value.strip())

        query.update(**{k: ", ".join(v) for k, v in result.items()})

    return query


class SQLRecord(logging.LogRecord):
    def getMessage(self):
        data = {}
        sqls = []
        request = threadlocal.get_current_request()
        if request:
            if not hasattr(request, "durations"):
                request.durations = []
                request.sqls = []
                request.start = time.monotonic()
            data["time"] = round(1000 * (time.monotonic() - request.start), 1)
        if "django.db" in self.name:
            if self.name == "django.db.backends" and hasattr(self, "duration"):
                duration, sql = self.duration, self.sql
            elif self.name == "django.db.backends":
                duration, sql, *_ = self.args
            elif self.name == "django.db.backends.schema":
                duration, sql = 0, self.args[0] % (self.args[1] or [])

            parsed_data = parse_sql_query(sql, 1000 * duration)
            sqls.append(parsed_data.get("sql"))
            report_sql_query(parsed_data)
            data.update(parsed_data)

            if request:
                request.sqls.extend(sqls)
                request.durations.append(data)
            return ""

        elif self.name == "django.server":
            console.log(self.msg % self.args)
            return ""
        elif self.name == "qinspect.middleware":
            m = REQUEST_TIMINGS_PAT.search(self.msg)
            if m:
                # report_queries(request.durations)
                report_durations(*map(int, m.groups()))
                return ""
        # elif self.name == "microservice.microservice":
        #     console.print(json.loads(self.args[0]))
        #     return ""
        # else:
        #     console.print(vars(self))

        return super().getMessage()
