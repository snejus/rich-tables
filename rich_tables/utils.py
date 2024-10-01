from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from itertools import groupby, islice, starmap, zip_longest
from math import copysign
from pprint import pformat
from string import ascii_uppercase, punctuation
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Match,
    Optional,
    Protocol,
    Sequence,
    SupportsFloat,
    Tuple,
    TypeVar,
    Union,
)

import platformdirs
import sqlparse
from multimethod import multimethod
from rich import box
from rich.align import Align
from rich.bar import Bar
from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

JSONDict = Dict[str, Any]
SPLIT_PAT = re.compile(r"[;,] ?")
PRED_COLOR_PAT = re.compile(r"(pred color)\]([^\[]+)")
HTML_PARAGRAPH = re.compile(r"</?p>")


BOLD_GREEN = "b green"
BOLD_RED = "b red"
SECONDS_PER_DAY = 86400
CONSECUTIVE_SPACE = re.compile("(?:^ +)|(?: +$)")


_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsDunderLT(Protocol[_T_contra]):
    def __lt__(self, __other: _T_contra) -> bool:
        pass


T = TypeVar("T")
K = TypeVar("K", bound=SupportsDunderLT[Any])


def sortgroup_by(
    iterable: Iterable[T], key: Callable[[T], K]
) -> List[Tuple[K, List[T]]]:
    return [(k, list(g)) for k, g in groupby(sorted(iterable, key=key), key)]


def format_string(text: str) -> str:
    if "pred color]" in text:
        return PRED_COLOR_PAT.sub(fmt_pred_color, text)
    if "[" in text and r"\[" not in text and "[/" not in text:
        return text.replace("[", r"\[")

    return text


def wrap(text: str, tag: str) -> str:
    return f"[{tag}]{format_string(str(text))}[/]"


def format_space(string: str) -> str:
    return CONSECUTIVE_SPACE.sub(r"[u]\g<0>[/]", string)


def format_new(string: str) -> str:
    return wrap(format_space(string), BOLD_GREEN)


def format_old(string: str) -> str:
    return wrap(wrap(string, BOLD_RED), "s")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    if change == "delete":
        return format_old(before)
    if change == "replace":
        return format_old(before) + format_new(after)

    return wrap(before, "dim")


def make_difftext(
    before: str,
    after: str,
    junk: str = "".join(
        sorted((set(punctuation) - {"_", "-", ":"}) | set(ascii_uppercase))
    ),
) -> str:
    matcher = SequenceMatcher(
        lambda x: x not in junk, autojunk=False, a=before, b=after
    )
    return "".join(
        fmtdiff(code, before[a1:a2], after[b1:b2]) or ""
        for code, a1, a2, b1, b2 in matcher.get_opcodes()
    )


def duration2human(duration: SupportsFloat) -> str:
    diff = timedelta(seconds=float(duration))
    days = f"{diff.days}d " if diff.days else ""
    time_parts = [diff.seconds // 3600, diff.seconds % 3600 // 60, diff.seconds % 60]
    return "{:>12}".format(days + ":".join(map("{0:0>2}".format, time_parts)))


def fmt_time(seconds: int) -> Iterable[str]:
    abs_seconds = abs(seconds)
    return (
        f"{int(copysign(num, seconds)):>3}{unit}"
        for num, unit in (
            (abs_seconds // 86400, "d"),
            (abs_seconds // 3600, "h"),
            (abs_seconds % 3600 // 60, "m"),
            (abs_seconds % 60, "s"),
        )
        if num
    )


def get_theme() -> Optional[Theme]:
    config_path = platformdirs.user_config_path("rich") / "config.ini"
    return Theme.read(str(config_path)) if config_path.exists() else None


def make_console(**kwargs: Any) -> Console:
    return Console(
        theme=get_theme(),
        force_terminal=True,
        force_interactive=False,
        emoji=True,
        **kwargs,
    )


console = make_console()
print = console.print


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


def predictably_random_color(string: str) -> str:
    random.seed(string.strip())

    return f"#{_randint():02X}{_randint():02X}{_randint():02X}"


def _format_with_color(string: str, on: Optional[str] = None) -> str:
    color = f"b {predictably_random_color(string)}"
    if on:
        color += f" on {on}"
    return wrap(string, color)


def split_with_color(text: str) -> str:
    return " ".join(_format_with_color(str(x)) for x in sorted(SPLIT_PAT.split(text)))


def format_with_color(items: str | Sequence[str]) -> str:
    if isinstance(items, str):
        items = [items]

    return " ".join(_format_with_color(str(x)) for x in items)


def format_with_color_on_black(items: Union[str, Iterable[str]]) -> str:
    if not isinstance(items, Iterable) or isinstance(items, str):
        items = sorted(SPLIT_PAT.split(str(items)))

    sep = wrap("a", "#000000 on #000000")
    return " ".join(
        sep + _format_with_color(str(item), on="#000000") + sep for item in items
    )


def fmt_pred_color(m: Match[str]) -> str:
    return f"{predictably_random_color(m.group(2))}]{m.group(2)}"


def simple_panel(content: RenderableType, **kwargs) -> Panel:
    kwargs.setdefault("title_align", "left")
    kwargs.setdefault("subtitle_align", "right")
    kwargs.setdefault("box", box.SIMPLE)
    kwargs.setdefault("expand", False)
    kwargs.setdefault("border_style", "red")
    if "title" in kwargs:
        kwargs["title"] = wrap(kwargs["title"], "b")
    if kwargs.pop("align", "") == "center":
        content = Align.center(content, vertical="middle")
    return Panel(content, **kwargs)


def border_panel(content: RenderableType, **kwargs) -> Panel:
    kwargs.setdefault("box", box.ROUNDED)
    kwargs.setdefault("border_style", "dim")
    return simple_panel(content, **kwargs)


def md_panel(content: str, **kwargs: Any) -> Panel:
    if "title" not in kwargs and (
        m := re.match(r"\[title\](.+?)\[/title\]\s+", content)
    ):
        kwargs["title"] = m[1]
        content = content.replace(m[0], "")

    return border_panel(
        Markdown(
            HTML_PARAGRAPH.sub("", content),
            inline_code_theme="nord-darker",
            code_theme="nord-darker",
            justify=kwargs.pop("justify", "left"),
        ),
        **kwargs,
    )


def new_tree(
    values: Iterable[RenderableType] = None, title: str = "", **kwargs: Any
) -> Tree:
    if values is None:
        values = []
    color = predictably_random_color(title or str(values))
    default: JSONDict = {"guide_style": color, "highlight": True}
    tree = Tree(title, **{**default, **kwargs})

    for val in values:
        tree.add(val)
    return tree


def get_country(code: str) -> str:
    return format_with_color(code)


def progress_bar(
    size: float, width: float, end: Optional[float] = None, inverse: bool = False
) -> Bar:
    if end is None:
        end = size
        size = width
        bgcolor = "black"
    else:
        bgcolor = "#252c3a"
    ratio = end / size if size else 1
    if inverse:
        ratio = 1 - ratio

    random.seed(str(width))

    def norm() -> int:
        return round(_randint() * ratio)

    color = f"#{norm():0>2X}{norm():0>2X}{norm():0>2X}"
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

    return f"{wrap(fmted, BOLD_RED if diff < 0 else BOLD_GREEN)} {strtime}"


def syntax(*args: Any, **kwargs: Any) -> Syntax:
    default = {
        "theme": "paraiso-dark",
        "background_color": "black",
        "word_wrap": True,
    }
    return Syntax(*args, **default | kwargs)


def sql_syntax(sql_string: str) -> Syntax:
    return Syntax(
        sqlparse.format(
            sql_string,
            indent_columns=True,
            strip_whitespace=True,
            strip_comments=True,
            reindent=True,
            reindent_aligned=False,
        ),
        "sql",
        theme="gruvbox-dark",
        background_color="black",
        word_wrap=True,
    )


def diff_serialize(value: Any) -> str:
    if value is None:
        return "null"
    return '""' if value == "" else str(value)


@multimethod
def diff(before: str, after: str) -> Any:
    return make_difftext(before, after)


@diff.register
def _(before: Any, after: Any) -> Any:
    return diff(diff_serialize(before), diff_serialize(after))


@diff.register
def _(before: List[Any], after: List[Any]) -> Any:
    return list(starmap(diff, zip_longest(before, after)))


@diff.register
def _(before: List[str], after: List[str]) -> Any:
    before_set, after_set = set(before), set(after)
    common = before_set & after_set
    common_list = list(common)
    return [
        *list(starmap(diff, zip(common_list, common_list))),
        *[
            diff(before or "", after or "")
            for before, after in zip_longest(
                list(before_set - common), list(after_set - common)
            )
        ],
    ]


@diff.register
def _(before: dict, after: dict) -> Any:
    data = {}
    keys = sorted(before.keys() | after.keys())
    for key in keys:
        if key not in before:
            data[wrap(key, BOLD_GREEN)] = wrap(diff_serialize(after[key]), BOLD_GREEN)
        elif key not in after:
            data[wrap(key, BOLD_RED)] = wrap(diff_serialize(before[key]), BOLD_RED)
        else:
            data[key] = diff(before[key], after[key])

    return data


def pretty_diff(before: Any, after: Any) -> Text:
    result = diff(before, after)
    if not isinstance(result, str):
        result = (
            pformat(result, indent=2, width=300, sort_dicts=False)
            .replace("'", "")
            .replace("\\\\", "\\")
        )

    return Text.from_markup(result)
