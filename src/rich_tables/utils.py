import itertools as it
import random
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import partial
from os import environ, path
from string import punctuation
from typing import (Any, Callable, Dict, Iterable, List, Optional,
                    SupportsFloat, Tuple, Type, Union)

# import sqlparse
from dateutil.parser import ParserError, parse
from ordered_set import OrderedSet as ordset
from pycountry import countries
from rich import box
from rich.align import Align
from rich.bar import Bar
from rich.console import Console, ConsoleRenderable, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme
from rich.tree import Tree

JSONDict = Dict[str, Any]
SPLIT_PAT = re.compile(r"[;,] | ")


def wrap(text: str, tag: str) -> str:
    return f"[{tag}]{text}[/]"


def format_new(string: str) -> str:
    return wrap(re.sub(r"(^\s+$)", "[u green]\\1[/]", string), "b green")


def format_old(string: str) -> str:
    return wrap(string, "b s red")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    elif change == "delete":
        return format_old(before)
    elif change == "replace":
        return format_old(before) + format_new(after)
    else:
        return wrap(before, "dim")


def make_difftext(
    before: str,
    after: str,
    junk: str = "".join(set(punctuation)) + " ",
    # junk: str = ascii_lowercase + "\n ",
    # before: str, after: str, junk: str = r" \n"
) -> str:
    before = re.sub(r"\\?\[", r"\\[", before)
    after = re.sub(r"\\?\[", r"\\[", after)

    matcher = SequenceMatcher(lambda x: x in junk, autojunk=False, a=before, b=after)
    # matcher = SequenceMatcher(autojunk=False, a=before, b=after)
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    # print("".join(sorted(matcher.bjunk, key=lambda x: after.index(x))))
    return diff


def fmt_time(diff: timedelta, pad: bool = True) -> Iterable[str]:
    opts: List[Tuple[int, str]] = [
        (diff.days, "d"),
        (diff.seconds // 3600, "h"),
        (diff.seconds % 3600 // 60, "min"),
        (diff.seconds % 60, "s"),
    ]
    fmt = "{:>3}{}" if pad else "{}{}"
    return it.starmap(fmt.format, filter(lambda x: x[0], opts))  # type: ignore


def duration2human(duration: SupportsFloat, acc: int = 1) -> str:
    # return " ".join(it.islice(fmt_time(timedelta(seconds=float(duration))), acc))
    diff = timedelta(seconds=float(duration))
    return ":".join(
        map(
            lambda x: str(x).zfill(2),
            [
                diff.days * 24 + diff.seconds // 3600,
                diff.seconds % 3600 // 60,
                diff.seconds % 60,
            ],
        )
    )


def time2human(
    timestamp: Union[int, str], acc: int = 1, use_colors=True, pad: bool = False
) -> str:
    if isinstance(timestamp, str):
        try:
            seconds = parse(timestamp).timestamp()
        except ParserError:
            try:
                seconds = int(float(timestamp))
            except ValueError:
                seconds = 0
    else:
        seconds = timestamp
    if not seconds:
        return "-"
    strtime = str(datetime.fromtimestamp(int(seconds)))
    diff = time.time() - seconds
    fmted = " ".join(it.islice(fmt_time(timedelta(seconds=abs(diff)), pad), acc))

    fut, past = (
        ("[b green]{}[/]", "[b red]-{}[/]") if use_colors else ("in {}", "{} ago")
    )
    return strtime + " " + past.format(fmted) if diff > 0 else fut.format(fmted)


def get_theme():
    return Theme.read(
        path.join(
            environ.get("XDG_CONFIG_HOME") or path.expanduser("~/.config"),
            "rich",
            "config.ini",
        )
    )


def make_console(**kwargs):
    return Console(
        theme=get_theme(), force_terminal=True, force_interactive=True, **kwargs
    )


class NewTable(Table):
    def __init__(self, *args, **kwargs) -> None:
        ckwargs = dict(
            overflow=kwargs.pop("overflow", "fold"),
            justify=kwargs.pop("justify", "left"),
            vertical=kwargs.pop("vertical", "top"),
        )
        super().__init__(**kwargs)
        for arg in args:
            self.add_column(arg, **ckwargs)

    def add_rows(self, rows: Iterable) -> None:
        """Add multiple rows to the table."""
        for row in rows:
            self.add_row(*row)

    @property
    def colnames(self) -> List[str]:
        """Provide a mapping between columns names / ids and columns."""
        return [str(c.header) for c in self.columns]

    @property
    def colmap(self) -> Dict[str, int]:
        """Provide a mapping between columns names / ids and columns."""
        return {str(c.header): c._index for c in self.columns if c.header}

    def add_dict_item(
        self, item: JSONDict, transform: Callable = lambda x, y: x, **kwargs
    ) -> None:
        """Take the required columns / keys from the given dictionary item."""
        self.add_row(*(transform(item.get(c, ""), c) for c in self.colnames), **kwargs)


def new_table(*args: Any, **kwargs: Any) -> NewTable:
    default: JSONDict = dict(
        border_style="black",
        show_edge=False,
        show_lines=False,
        show_header=False,
        highlight=True,
        row_styles=["white"],
        expand=True,
        title_justify="left",
    )
    if args:
        default.update(
            header_style="bold misty_rose1", box=box.SIMPLE_HEAVY, show_header=True
        )
    rows = kwargs.pop("rows", [])
    table = NewTable(*args, **{**default, **kwargs})
    if rows:
        table.add_rows(rows)
    return table


def predictably_random_color(string: str) -> str:
    random.seed(string)
    rand = partial(random.randint, 60, 190)
    return "#{:0>2X}{:0>2X}{:0>2X}".format(rand(), rand(), rand())


def format_with_color(name: str) -> str:
    return wrap(name, f"b {predictably_random_color(name)}")


def simple_panel(content: RenderableType, **kwargs: Any) -> Panel:
    default: JSONDict = dict(
        title_align="left", subtitle_align="right", box=box.SIMPLE, expand=False
    )
    if "title" in kwargs:
        kwargs["title"] = wrap(kwargs["title"], "b")
    if kwargs.pop("align", "") == "center":
        content = Align.center(content, vertical="middle")
    return Panel(content, **{**default, **kwargs})


def border_panel(content: RenderableType, **kwargs: Any) -> Panel:
    return simple_panel(
        content, **{**dict(box=box.ROUNDED, border_style="dim"), **kwargs}
    )


def md_panel(content: str, **kwargs: Any) -> Panel:
    return simple_panel(
        Markdown(
            # re.sub(
            #     r"```\n",
            #     "```python\n",
            #     content.replace("suggestion", "python"),
            #     count=1,
            # )
            content.replace("suggestion", "python"),
        ),
        **kwargs,
    )


def new_tree(
    values: Iterable[ConsoleRenderable] = [], title: str = "", **kwargs
) -> Tree:
    color = predictably_random_color(title or str(values))
    default: JSONDict = dict(guide_style=color)
    tree = Tree(wrap(title, "b"), **{**default, **kwargs})

    for val in values:
        tree.add(val)
    return tree


def get_country(code: str) -> str:
    try:
        country = (
            countries.lookup(code)
            .name.replace("Russian Federation", "Russia")
            .replace("Czechia", "Czech Republic")
            .replace("North Macedonia", "Macedonia")
            .replace("Korea, Republic of", "South Korea")
        )
        return f":flag_for_{country.lower().replace(' ', '_')}: {country}"
    except LookupError:
        return "Worldwide"


def colored_with_bg(string: str) -> str:
    return wrap(f" {string} ", f"bold {predictably_random_color(string)} on #000000")


def _colored_split(strings: List[str]) -> str:
    return "  ".join(map(format_with_color, strings))


def unsorted_colored_split(string: str) -> str:
    return _colored_split(SPLIT_PAT.split(string))


def colored_split(string: str) -> str:
    return _colored_split(sorted(SPLIT_PAT.split(string)))


def progress_bar(
    count: float, total_max: float, item_max: Optional[float] = None
) -> Bar:
    use_max = total_max
    if item_max is not None:
        use_max = item_max
    ratio = count / use_max if use_max else 0
    random.seed(str(total_max))
    rand = partial(random.randint, 50, 180)

    def norm():
        return round(rand() * ratio)

    color = "#{:0>2X}{:0>2X}{:0>2X}".format(norm(), norm(), norm())
    return Bar(use_max, 0, count, color=color)


def _get_val(value: Any, field: str) -> str:
    return FIELDS_MAP[field](value) if value is not None else ""


def get_val(obj: JSONDict, field: str) -> str:
    return _get_val(obj.get(field), field)


def counts_table(data: List[JSONDict], header: str = "") -> Table:
    keys = ordset(data[0])
    count_col_name = "count"
    if count_col_name not in keys:
        first = data[0]
        for key in keys:
            if key != "total" and isinstance(first[key], (int, float)):
                count_col_name = key

    all_counts = {float(i.get(count_col_name, 0)) for i in data}
    num_type: Type = float
    if len({c % 1 for c in all_counts}) == 1:
        num_type = int
    total_max = max(all_counts)

    # ensure count_col is at the end
    headers = keys - {count_col_name, "total"}
    table = new_table(*headers, "", count_col_name, overflow="fold", vertical="middle")
    for item in data:
        item_count = float(item.pop(count_col_name, 0))
        item_max = item.pop("total", None)
        if item_max is not None:
            item_max = float(item_max)
            item_table_val = f"{num_type(item_count)}/{num_type(item_max)}"
        elif "duration" in count_col_name:
            item_table_val = duration2human(item_count, 2)
        else:
            item_table_val = str(num_type(item_count))
        table.add_row(
            *map(lambda x: get_val(item, x), headers),
            item_table_val,
            progress_bar(item_count, total_max, item_max=item_max),
        )
    if count_col_name in {"duration", "total_duration"}:
        table.caption = "Total " + duration2human(float(sum(all_counts)), 2)
        table.caption_justify = "left"
    if header:
        table.title = header
    return table


def timestamp2isotime(timestamp: Optional[int]) -> str:
    return datetime.fromtimestamp(timestamp or 0, tz=timezone.utc).time().isoformat()


FIELDS_MAP: Dict[str, Callable] = defaultdict(
    lambda: str,
    albumtypes=lambda x: "; ".join(
        map(
            format_with_color,
            {
                "album; compilation": "comp",
                "dj-mix; broadcast": "dj-mix",
                "broadcast; dj-mix": "dj-mix",
            }
            .get(x, x)
            .split("; "),
        )
    ),
    author=lambda x: colored_with_bg(x)
    if isinstance(x, str)
    else x["login"]
    if isinstance(x, dict)
    else x,
    user=format_with_color,
    bodyHTML=md_panel,
    label=format_with_color,
    labels=lambda x: " ".join(wrap(y["name"], f"b #{y['color']}") for y in x)
    if isinstance(x, list)
    else x,
    catalognum=format_with_color,
    last_played=lambda x: time2human(x, use_colors=True),
    avg_last_played=lambda x: time2human(x, acc=2, use_colors=True),
    since=lambda x: x
    if isinstance(x, str)
    else datetime.fromtimestamp(x).strftime("%F %H:%M"),
    mtime=time2human,
    added=time2human,
    createdAt=time2human,
    committedDate=time2human,
    bpm=lambda x: wrap(
        x,
        "green"
        if int(x or 0) < 135
        else "b blink red"
        if int(x or 0) > 230
        else "red"
        if int(x or 0) > 165
        else "yellow",
    ),
    style=format_with_color,
    genre=colored_split,
    length=timestamp2isotime,
    tracktotal=lambda x: (wrap("{}", "b cyan") + "/" + wrap("{}", "b cyan")).format(*x)
    if isinstance(x, Iterable) and not isinstance(x, str)
    else str(x),
    country=get_country,
    data_source=format_with_color,
    helicopta={1: wrap(" ", "b red"), 0: "", None: ""}.get,
    keywords=lambda x: " ".join(map(colored_with_bg, colored_split(x).split("  ")))
    if isinstance(x, str)
    else x,
    ingr=lambda x: simple_panel(colored_split(x)),
    content=lambda x: md_panel(x) if isinstance(x, str) else x,
    notes=md_panel,
    text=md_panel,
    instructions=md_panel,
    comments=lambda x: md_panel(
        x.replace("\n0", "\n* 0").replace("\n[", "\n* ["), title="comments"
    ),
    tags=colored_split,
    released=lambda x: x.replace("-00", "") if isinstance(x, str) else str(x),
    # desc=md_panel,
    calendar=format_with_color,
    source=format_with_color,
    category=format_with_color,
    categories=colored_split,
    price=lambda x: colored_with_bg(str(x)),
    interview=md_panel,
    benefits=md_panel,
    primary=lambda x: colored_split if isinstance(x, str) else str(x),
    **{"from": format_with_color},
    to=format_with_color,
    creditText=md_panel,
    duration=lambda x: duration2human(x, 2) if isinstance(x, (int, float)) else x,
    total_duration=lambda x: duration2human(x, 2),
    brand=format_with_color,
    mastering=format_with_color,
    answer=md_panel,
    plays=lambda x: wrap(x, "b green"),
    skips=lambda x: wrap(x, "b red"),
    name=lambda x: wrap(x, "b"),
    description=lambda x: wrap(x, "i"),
    kind=colored_split,
    type_name=format_with_color,
    table=format_with_color,
    endpoint=format_with_color,
    issuetype=format_with_color,
    priority=format_with_color,
    status=format_with_color,
    key=format_with_color,
    assignee=format_with_color,
    subtask_priority=format_with_color,
    subtask_status=format_with_color,
    subtask_key=format_with_color,
    subtask_assignee=format_with_color,
    epic_priority=format_with_color,
    epic_status=format_with_color,
    epic_key=format_with_color,
    Category=format_with_color,
    Description=format_with_color,
    link=format_with_color,
    context=lambda x: Syntax(
        x, "python", theme="paraiso-dark", background_color="black", word_wrap=True
    ),
    sql=lambda x: Syntax(
        x.replace("'", ""),
        "sql",
        theme="paraiso-dark",
        background_color="black",
        word_wrap=True,
    ),
    # message=lambda x: Syntax(
    #     sqlparse.format(
    #         re.sub(r"..traceback_psycopg2.*", "", x).replace('"', ""),
    #         reindent=True,
    #     ),
    #     lexer="sql",
    #     theme="gruvbox-dark",
    #     background_color="black",
    # ),
)
FIELDS_MAP["Samanza Hussain"] = lambda x: wrap(
    x, predictably_random_color("Samanza Hussain")
)
FIELDS_MAP["Francesca Hess"] = lambda x: wrap(
    x, predictably_random_color("Francesca Hess")
)

DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "last_played": ":timer_clock: ",
    "mtime": "updated",
    "data_source": "source",
    "helicopta": "[dark red]:helicopter:[/]",
    "track_alt": ":cd:",
    "catalognum": "📖",
    "plays": "[green]:play_button:[/]",
    "skips": "[red]:stop_button:[/]",
    "albumtypes": "types",
}
