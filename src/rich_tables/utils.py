import random
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache, partial, singledispatch
from itertools import islice
from math import copysign
from os import environ, path
from string import punctuation, whitespace
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    SupportsFloat,
    Type,
    Union,
)

from rich import box
from rich.align import Align
from rich.bar import Bar
from rich.console import Console, ConsoleRenderable, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

JSONDict = Dict[str, Any]
SPLIT_PAT = re.compile(r"[;,] ?")


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
    before: str, after: str, junk: str = set(punctuation + r"\n\t") - {"_"}
) -> str:
    before = re.sub(r"\\?\[", r"\\[", before)
    after = re.sub(r"\\?\[", r"\\[", after)

    matcher = SequenceMatcher(
        lambda x: x in junk, autojunk=False, a=before, b=after
    )
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    return diff


def duration2human(duration: SupportsFloat, acc: int = 1) -> str:
    diff = timedelta(seconds=float(duration))
    days = f"{diff.days}d " if diff.days else ""
    return "{:>12}".format(
        days
        + ":".join(
            map(
                lambda x: str(x).zfill(2),
                [diff.seconds // 3600, diff.seconds % 3600 // 60, diff.seconds % 60],
            )
        )
    )


def fmt_time(seconds: int) -> Iterable[str]:
    abs_seconds = abs(seconds)
    return (
        "{:>3}{}".format(int(copysign(num, seconds)), unit)
        for num, unit in (
            (abs_seconds // 86400, "d"),
            (abs_seconds // 3600, "h"),
            (abs_seconds % 3600 // 60, "m"),
            (abs_seconds % 60, "s"),
        )
        if num
    )


def get_theme() -> Optional[Theme]:
    _path = path.join(
        environ.get("XDG_CONFIG_HOME") or path.expanduser("~/.config"),
        "rich",
        "config.ini",
    )
    if path.exists(_path):
        return Theme.read(_path)
    return None


def make_console(**kwargs: Any) -> Console:
    return Console(
        theme=get_theme(),
        force_terminal=True,
        force_interactive=True,
        emoji=True,
        **kwargs,
    )


class NewTable(Table):
    def __init__(self, *args: str, **kwargs: Any) -> None:
        ckwargs = dict(
            overflow=kwargs.pop("overflow", "fold"),
            justify=kwargs.pop("justify", "left"),
            vertical=kwargs.pop("vertical", "middle"),
        )
        super().__init__(**kwargs)
        for idx, arg in enumerate(args):
            self.add_column(arg, **ckwargs)

    def add_rows(self, rows: Iterable[Iterable[RenderableType]]) -> None:
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
        self,
        item: JSONDict,
        transform: Callable[[Any, str], Any] = lambda x, y: x,
        **kwargs: Any,
    ) -> None:
        """Take the required columns / keys from the given dictionary item."""
        vals = (transform(item.get(c), c) for c in self.colnames)
        self.add_row(*vals, **kwargs)


def new_table(*headers: str, **kwargs: Any) -> NewTable:
    default = dict(
        border_style="black",
        show_edge=False,
        show_header=False,
        pad_edge=False,
        highlight=True,
        row_styles=["white"],
        expand=False,
        title_justify="left",
        show_lines=False,
    )
    if headers:
        default.update(
            header_style="bold misty_rose1", box=box.SIMPLE_HEAVY, show_header=True
        )
    rows = kwargs.pop("rows", [])
    table = NewTable(*headers, **{**default, **kwargs})
    if rows:
        table.add_rows(rows)
    return table


def list_table(items: Iterable[Any], **kwargs) -> NewTable:
    return new_table(rows=[[i] for i in items], **kwargs)


@lru_cache(None)
def predictably_random_color(string: str) -> str:
    random.seed(string)
    rand = partial(random.randint, 60, 200)
    return "#{:02X}{:02X}{:02X}".format(rand(), rand(), rand())


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
        Markdown(content, justify=kwargs.pop("justify", "left")), **kwargs
    )


def new_tree(
    values: Iterable[ConsoleRenderable] = [], title: str = "", **kwargs
) -> Tree:
    color = predictably_random_color(title or str(values))
    default: JSONDict = dict(guide_style=color, highlight=True)
    tree = Tree(wrap(title, "b"), **{**default, **kwargs})

    for val in values:
        tree.add(val)
    return tree


def get_country(code: str) -> str:
    return format_with_color(code)
    # try:
    #     # country = (
    #     #     pycountry.countries.lookup(code)
    #     #     .name.replace("Russian Federation", "Russia")
    #     #     .replace("Czechia", "Czech Republic")
    #     #     .replace("North Macedonia", "Macedonia")
    #     #     .replace("Korea, Republic of", "South Korea")
    #     # )
    #     country = "Russia"
    #     return f":flag_for_{country.lower().replace(' ', '_')}: {country}"
    # except LookupError:
    #     return "Worldwide"


def colored_with_bg(string: str) -> str:
    sep = wrap("a", "#000000 on #000000")
    return (
        sep + wrap(string, f"bold {predictably_random_color(string)} on #000000") + sep
    )


def _colored_split(strings: List[str]) -> str:
    return " ".join(map(format_with_color, strings))


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


def _get_val(value: Any, field: str) -> Any:
    return FIELDS_MAP[field](value) if value is not None else ""


@singledispatch
def get_val(obj: Union[JSONDict, object], field: str) -> Any:
    """Definition of a generic get_val function."""


@get_val.register
def get_val_from_dict(obj: dict, field: str) -> Any:
    return _get_val(obj.get(field), field)


@get_val.register
def get_val_from_object(obj: object, field: str) -> Any:
    return _get_val(getattr(obj, field, None), field)


def counts_table(data: List[JSONDict], count_key: str, header: str = "") -> Table:
    keys = dict.fromkeys(data[0])

    all_counts = {float(i.get(count_key) or 0) for i in data}
    num_type: Type = float
    if len({c % 1 for c in all_counts}) == 1:
        num_type = int
    total_max = max(all_counts)

    # ensure count_col is at the end
    headers = [k for k in keys if k not in {count_key, "total"}]
    table = new_table(*headers, count_key, "")
    for item in data:
        item_count = float(item.pop(count_key) or 0)
        item_max = item.pop("total", None)
        if item_max is not None:
            item_max = float(item_max)
            item_table_val = f"{num_type(item_count)}/{num_type(item_max)}"
        elif "duration" in count_key:
            item_table_val = duration2human(item_count, 2)
        else:
            item_table_val = str(num_type(item_count))
        table.add_row(
            *map(lambda x: get_val(item, x), headers),
            item_table_val,
            progress_bar(item_count, total_max, item_max=item_max),
        )
    if count_key in {"duration", "total_duration"}:
        table.caption = "Total " + duration2human(float(sum(all_counts)), 2)
        table.caption_justify = "left"
    if header:
        table.title = header
    return table


def timestamp2datetime(timestamp: Union[str, int, float, None]) -> datetime:
    if isinstance(timestamp, str):
        timestamp = re.sub(r"[.]\d+", "", timestamp.strip("'"))
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y%m%dT%H%M%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(timestamp, fmt)
            except ValueError:
                pass
    return datetime.fromtimestamp(int(float(timestamp or 0)), tz=timezone.utc)


def timestamp2datetimestr(timestamp: Union[str, int, float, None]) -> str:
    return timestamp2datetime(timestamp).strftime("%F %T")


def timestamp2timestr(timestamp: Union[str, int, float, None]) -> str:
    return timestamp2datetime(timestamp).strftime("%T")


def time2human(timestamp: Union[int, str], acc: int = 1) -> str:
    try:
        datetime = timestamp2datetime(timestamp)
    except ValueError:
        return timestamp
    diff = datetime.timestamp() - time.time()
    fmted = " ".join(islice(fmt_time(int(diff)), acc))

    if abs(diff) > 86000:
        strtime = datetime.strftime("%F")
    else:
        strtime = datetime.strftime("%T")

    return "[b {}]{}[/]".format("red" if diff < 0 else "green", fmted) + " " + strtime


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
    author=colored_with_bg,
    # participants=lambda x: "  ".join(map(colored_with_bg, x)),
    user=format_with_color,
    bodyHTML=md_panel,
    # desc=md_panel,
    label=format_with_color,
    labels=lambda x: wrap(
        "    ".join(wrap(y["name"].upper(), f"#{y['color']}") for y in x), "b i"
    )
    if isinstance(x, list)
    else colored_split(x),
    catalognum=format_with_color,
    last_played=time2human,
    avg_last_played=lambda x: time2human(x, acc=2),
    since=lambda x: x
    if isinstance(x, str)
    else datetime.fromtimestamp(float(x)).strftime("%F %H:%M"),
    mtime=time2human,
    dt=lambda x: time2human(x, 5),
    start=time2human,
    end=time2human,
    added=time2human,
    entry=time2human,
    due=time2human,
    created=time2human,
    # createdAt=lambda x: x if "[/]" in x else time2human(x),
    # updatedAt=time2human,
    createdAt=lambda x: x.replace("T", " ").replace("Z", ""),
    updatedAt=lambda x: x.replace("T", " ").replace("Z", ""),
    modified=time2human,
    updated=time2human,
    wait_per_play=lambda x: wrap(
        " ".join(islice(fmt_time(int(float(x))), 1)), "b green"
    ),
    committedDate=time2human,
    bpm=lambda x: wrap(
        str(x),
        "green"
        if int(x or 0) < 135
        else "b red"
        if int(x or 0) > 230
        else "red"
        if int(x or 0) > 165
        else "yellow",
    )
    if isinstance(x, int)
    else x,
    style=format_with_color,
    __typename=format_with_color,
    genre=colored_split,
    group_source=lambda x: ", ".join(map(format_with_color, x)),
    length=timestamp2timestr,
    tracktotal=lambda x: (wrap("{}", "b cyan") + "/" + wrap("{}", "b cyan")).format(*x)
    if isinstance(x, Iterable) and not isinstance(x, str)
    else str(x),
    country=get_country,
    data_source=format_with_color,
    helicopta=lambda x: ":fire: " if x and int(x) else "",
    hidden=lambda x: ":shit: " if x and int(x) else "",
    keywords=lambda x: " ".join(map(colored_with_bg, colored_split(x).split("  ")))
    if isinstance(x, str)
    else x,
    ingr=lambda x: simple_panel(colored_split(x)),
    content=lambda x: md_panel(x) if isinstance(x, str) else x,
    notes=md_panel,
    text=md_panel,
    instructions=md_panel,
    comment=md_panel,
    comments=lambda x: md_panel(
        x.replace("\n0", "\n* 0").replace("\n[", "\n* ["), title="comments"
    ),
    tags=colored_split,
    released=lambda x: x.replace("-00", "") if isinstance(x, str) else str(x),
    calendar=format_with_color,
    source=format_with_color,
    category=format_with_color,
    categories=colored_split,
    # price=lambda x: colored_with_bg(str(x)),
    interview=md_panel,
    benefits=md_panel,
    primary=lambda x: colored_split(x) if isinstance(x, str) else str(x),
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
    # name=lambda x: wrap(x, "b"),
    description=md_panel,
    # body=md_panel,
    event=format_with_color,
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
    symbol=format_with_color,
    module=format_with_color,
    code=format_with_color,
    entity=format_with_color,
    new=lambda x: "[b green]:heavy_check_mark:[/]"
    if x
    else "[b red]:cross_mark_button:[/]",
    message=lambda x: border_panel(
        Syntax(
            x,
            "diff",
            theme="paraiso-dark",
            background_color="black",
            word_wrap=True,
            indent_guides=True,
        )
    ),
    link=lambda x: {
        "blocks": lambda y: wrap(f" {y} ", "b black on red"),
        "is blocked by": lambda y: wrap(y, "b red"),
    }.get(x, lambda x: x)(x),
    album=format_with_color,
    context=lambda x: Syntax(
        x, "python", theme="paraiso-dark", background_color="black", word_wrap=True
    ),
    python=lambda x: Syntax(
        x, "python", theme="paraiso-dark", background_color="black", word_wrap=True
    ),
    CreatedBy=lambda x: Syntax(
        x.replace(";", "\n"),
        "sh",
        theme="paraiso-dark",
        background_color="black",
        word_wrap=True,
    ),
    sql=lambda x: border_panel(
        Syntax(
            x.replace('"', ""),
            "sql",
            theme="gruvbox-dark",
            background_color="black",
            word_wrap=True,
        )
    ),
    file=lambda x: "/".join(map(format_with_color, x.split("/"))),
    field=lambda x: ".".join(map(format_with_color, x.split("."))),
    log=lambda x: border_panel(
        Syntax(
            x,
            "python",
            theme="paraiso-dark",
            background_color="black",
            word_wrap=True,
            indent_guides=True,
        )
    ),
    diff=lambda x: Text.from_markup(x) if "[/]" in x else md_panel(x),
    unified_diff=lambda x: Syntax(
        x, "diff", theme="paraiso-dark", background_color="black", word_wrap=True
    ),
    query=lambda x: Text(x, style="bold"),
)

DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "last_played": ":timer_clock: ",
    "mtime": "updated",
    "data_source": "source",
    "helicopta": "[dark red]:helicopter:[/]",
    "hidden": ":no_entry:",
    "track_alt": ":cd:",
    "catalognum": ":pen: ",
    "plays": "[green]:play_button:[/]",
    "skips": "[red]:stop_button:[/]",
    "albumtypes": "types",
}
