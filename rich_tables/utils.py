import random
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import islice, starmap, zip_longest
from math import copysign
from os import environ, path
from string import punctuation
from typing import Any, Callable, Dict, Iterable, List, Optional, SupportsFloat, Union

import platformdirs
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
SPLIT_PAT = re.compile(r"[;,] ?")
PRED_COLOR_PAT = re.compile(r"(pred color)\]([^\[]+)")


BOLD_GREEN = "b green"
BOLD_RED = "b red"
SECONDS_PER_DAY = 86400


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
    junk: str = "".join(set(punctuation) - {"_", "-", ":"}),
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
    _path = platformdirs.user_config_path("rich/config.ini")
        "config.ini",
    )
    if path.exists(_path):
        return Theme.read(_path)
    return None


def make_console(**kwargs: Any) -> Console:
    return Console(
        theme=get_theme(),
        force_terminal=True,
        force_interactive=False,
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
        for arg in args:
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
        vals = (transform(item.get(c, ""), c) for c in self.colnames)
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
        "style": "black",
        "border_style": "black",
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


def _randint() -> int:
    return random.randint(50, 205)


@lru_cache(None)
def predictably_random_color(string: str) -> str:
    random.seed(string.strip())

    return f"#{_randint():02X}{_randint():02X}{_randint():02X}"


@lru_cache(None)
def _format_with_color(string: str, on: Optional[str] = None) -> str:
    color = f"b {predictably_random_color(string)}"
    if on:
        color += f" on {on}"
    return wrap(string, color)


def split_with_color(text: str) -> str:
    return " ".join(_format_with_color(str(x)) for x in sorted(SPLIT_PAT.split(text)))


def format_with_color(items: Union[str, Iterable[str]]) -> str:
    if isinstance(items, str):
        items = [items]

    return " ".join((_format_with_color(str(x)) for x in items))


def format_with_color_on_black(items: Union[str, Iterable[str]]) -> str:
    if isinstance(items, str):
        items = sorted(SPLIT_PAT.split(items))

    sep = wrap("a", "#000000 on #000000")
    return " ".join(
        sep + _format_with_color(item, on="#000000") + sep for item in items
    )


def fmt_pred_color(m: re.Match) -> str:
    return f"{predictably_random_color(m.group(2))}]{m.group(2)}"


def format_string(text: str) -> str:
    if "pred color]" in text:
        return PRED_COLOR_PAT.sub(fmt_pred_color, text)
    if "[/]" not in text:
        return text.replace("[", r"\[")

    return text


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
    return border_panel(
        Markdown(
            content,
            inline_code_theme="nord-darker",
            code_theme="nord-darker",
            justify=kwargs.pop("justify", "left"),
        ),
        **kwargs,
    )


def new_tree(
    values: Iterable[RenderableType] = [], title: str = "", **kwargs: Any
) -> Tree:
    color = predictably_random_color(title or str(values))
    default: JSONDict = {"guide_style": color, "highlight": True}
    tree = Tree(title, **{**default, **kwargs})

    for val in values:
        tree.add(val)
    return tree


def get_country(code: str) -> str:
    return format_with_color(code)


def progress_bar(size: float, width: float, end: Optional[float] = None) -> Bar:
    if end is None:
        end = size
        size = width
        bgcolor = "black"
    else:
        bgcolor = "white"
    ratio = end / size

    random.seed(str(width))

    def norm() -> int:
        return round(_randint() * ratio)

    color = f"#{norm():0>2X}{norm():0>2X}{norm():0>2X}"
    # print(f"{end=} {size=} {width=}")
    return Bar(
        size=size, begin=0, width=int(width), end=end, color=color, bgcolor=bgcolor
    )


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


def human_dt(timestamp: Union[int, str, float], acc: int = 1) -> str:
    try:
        datetime = timestamp2datetime(timestamp)
    except ValueError:
        return str(timestamp)

    diff = datetime.timestamp() - time.time()
    fmted = " ".join(islice(fmt_time(int(diff)), acc))

    return wrap(fmted, BOLD_RED if diff < 0 else BOLD_GREEN)


def diff_dt(timestamp: Union[int, str, float], acc: int = 2) -> str:
    try:
        datetime = timestamp2datetime(timestamp)
    except ValueError:
        return str(timestamp)

    diff = datetime.timestamp() - time.time()
    fmted = " ".join(islice(fmt_time(int(diff)), acc))

    strtime = datetime.strftime("%F" if abs(diff) > SECONDS_PER_DAY else "%T")

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
def _(before: None, after: None) -> str:
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
