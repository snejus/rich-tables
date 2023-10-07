import random
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache, partial
from itertools import islice, starmap, zip_longest
from math import copysign
from os import environ, path
from string import punctuation
from typing import Any, Callable, Dict, Iterable, List, Optional, SupportsFloat, Union

from multimethod import multimethod
from rich import box
from rich.align import Align
from rich.bar import Bar
from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme
from rich.tree import Tree

JSONDict = Dict[str, Any]
SPLIT_PAT = re.compile(r"[;,\n] ?")


BOLD_GREEN = "b green"
BOLD_RED = "b red"


def wrap(text: str, tag: str) -> str:
    return f"[{tag}]{text}[/]"


def format_new(string: str) -> str:
    return wrap(re.sub(r"(^\s+$)", "[u green]\\1[/]", string), BOLD_GREEN)


def format_old(string: str) -> str:
    return wrap(wrap(string, BOLD_RED), "s")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    elif change == "delete":
        return format_old(before)
    elif change == "replace":
        return format_old(before) + format_new(after)

    return wrap(before, "dim")


def make_difftext(
    before: str,
    after: str,
    junk: str = "".join(set(punctuation) - {"_", ":"}),
) -> str:
    before = re.sub(r"\\?\[", r"\\[", before)
    after = re.sub(r"\\?\[", r"\\[", after)

    matcher = SequenceMatcher(
        lambda x: x not in junk, autojunk=False, a=before, b=after
    )
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    return diff


def duration2human(duration: SupportsFloat) -> str:
    diff = timedelta(seconds=float(duration))
    days = f"{diff.days}d " if diff.days else ""
    time_parts = [diff.seconds // 3600, diff.seconds % 3600 // 60, diff.seconds % 60]
    return "{:>12}".format(days + ":".join(map("{0:0>2}".format, time_parts)))


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
        ckwargs = {
            "overflow": kwargs.pop("overflow", "fold"),
            "justify": kwargs.pop("justify", "left"),
            "vertical": kwargs.pop("vertical", "middle"),
        }
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

    def add_dict_item(
        self,
        item: JSONDict,
        transform: Callable[[Any, str], Any] = lambda x, _: x,
        **kwargs: Any,
    ) -> None:
        """Take the required columns / keys from the given dictionary item."""
        vals = (transform(item.get(c) or "", c) for c in self.colnames)
        self.add_row(*vals, **kwargs)


def new_table(*headers: str, **kwargs: Any) -> NewTable:
    # print(f"creating new table, headers: {headers}")
    default = {
        "show_edge": False,
        "show_header": False,
        "pad_edge": False,
        "highlight": True,
        "row_styles": ["white"],
        "expand": False,
        "title_justify": "left",
        "style": "magenta",
        "border_style": "magenta",
        "box": box.ROUNDED,
    }
    if headers:
        default.update(
            header_style="bold misty_rose1", box=box.SIMPLE_HEAVY, show_header=True
        )
    rows = kwargs.pop("rows", [])
    table = NewTable(*headers, **{**default, **kwargs})
    if rows:
        table.add_rows(rows)
    return table


def list_table(items: Iterable[Any], **kwargs: Any) -> NewTable:
    return new_table(rows=[[i] for i in items], **kwargs)


@lru_cache(None)
def predictably_random_color(string: str) -> str:
    random.seed(string)
    rand = partial(random.randint, 60, 200)
    return "#{:02X}{:02X}{:02X}".format(rand(), rand(), rand())


def format_with_color(name: str) -> str:
    return wrap(name, f"b {predictably_random_color(name)}")


def simple_panel(content: RenderableType, **kwargs: Any) -> Panel:
    # print(f"creating new panel with title {kwargs.get('title')}")
    default: JSONDict = {
        "title_align": "left",
        "subtitle_align": "right",
        "box": box.SIMPLE,
        "expand": False,
        "border_style": "red",
    }
    if "title" in kwargs:
        kwargs["title"] = wrap(kwargs["title"], "b")
    if kwargs.pop("align", "") == "center":
        content = Align.center(content, vertical="middle")
    return Panel(content, **{**default, **kwargs})


def border_panel(content: RenderableType, **kwargs: Any) -> Panel:
    return simple_panel(
        content, **{"box": box.ROUNDED, "border_style": "dim", **kwargs}
    )


def md_panel(content: str, **kwargs: Any) -> Panel:
    return simple_panel(
        Markdown(content, justify=kwargs.pop("justify", "left")), **kwargs
    )


def new_tree(
    values: Iterable[RenderableType] = [], title: str = "", **kwargs: Any
) -> Tree:
    color = predictably_random_color(title or str(values))
    default: JSONDict = {"guide_style": color, "highlight": True}
    tree = Tree(wrap(title, "b"), **{**default, **kwargs})

    for val in values:
        tree.add(val)
    return tree


def get_country(code: str) -> str:
    return format_with_color(code)


def colored_with_bg(string: str) -> str:
    sep = wrap("a", "#000000 on #000000")
    return (
        sep + wrap(string, f"bold {predictably_random_color(string)} on #000000") + sep
    )


def _colored_split(strings: List[str]) -> str:
    return " ".join(map(format_with_color, strings))


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

    def norm() -> int:
        return round(rand() * ratio)

    color = "#{:0>2X}{:0>2X}{:0>2X}".format(norm(), norm(), norm())
    return Bar(use_max, 0, count, color=color)


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


def timestamp2timestr(timestamp: Union[str, int, float, None]) -> str:
    return timestamp2datetime(timestamp).strftime("%T")


def time2human(timestamp: Union[int, str, float], acc: int = 1) -> str:
    try:
        datetime = timestamp2datetime(timestamp)
    except ValueError:
        return str(timestamp)

    diff = datetime.timestamp() - time.time()
    fmted = " ".join(islice(fmt_time(int(diff)), acc))

    strtime = datetime.strftime("%F" if abs(diff) > 86000 else "%T")

    return wrap(fmted, BOLD_RED if diff < 0 else BOLD_GREEN) + " " + strtime


def syntax(*args: Any, **kwargs: Any) -> Syntax:
    default = {
        "theme": "paraiso-dark",
        "background_color": "black",
        "word_wrap": True,
    }
    return Syntax(*args, **{**default, **kwargs})


@multimethod
def diff(before: Any, after: Any) -> Any:
    return make_difftext(str(before), str(after))


@diff.register
def _(before: Any, after: None) -> str:
    return wrap(before, BOLD_RED)


@diff.register
def _(before: None, after: Any) -> str:
    return wrap(after, BOLD_GREEN)


@diff.register
def _(before: list, after: list) -> Any:
    return list(starmap(diff, zip_longest(before, after)))


@diff.register
def _(before: dict, after: dict) -> Any:
    data = {}
    keys = sorted(before.keys() | after.keys())
    for key in keys:
        if key not in before:
            data[wrap(key, BOLD_GREEN)] = wrap(after[key], BOLD_GREEN)
        elif key not in after:
            data[wrap(key, BOLD_RED)] = wrap(before[key], BOLD_RED)
        else:
            data[key] = diff(before.get(key), after.get(key))

    return data
