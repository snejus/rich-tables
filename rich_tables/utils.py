from __future__ import annotations

import colorsys
import random
import re
import time
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import groupby, islice, starmap, zip_longest
from math import copysign
from pprint import pformat
from re import Match
from string import printable, punctuation
from typing import TYPE_CHECKING, Any, Callable, Protocol, SupportsFloat, TypeVar

import humanize
import platformdirs
from multimethod import multimethod
from rich import box
from rich.align import Align, VerticalAlignMethod
from rich.bar import Bar
from rich.console import Console, ConsoleRenderable, RenderableType, RichCast
from rich.errors import MarkupError
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

if TYPE_CHECKING:
    from coloraide import Color

JSONDict = dict[str, Any]
T = TypeVar("T")


class Pat:
    SPLIT_PAT = re.compile(r"[;,] ?")
    PRED_COLOR_PAT = re.compile(r"(pred color)\]([^\[]+)")
    HTML_PARAGRAPH = re.compile(r"</?p>")
    CONSECUTIVE_SPACE = re.compile("(?:^ +)|(?: +$)")
    OPENING_BRACKET = re.compile(r"\[(?!http)")


BOLD_GREEN = "b green"
BOLD_RED = "b red"
SECONDS_PER_DAY = 86400


_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsDunderLT(Protocol[_T_contra]):
    def __lt__(self, __other: _T_contra) -> bool:
        pass


K = TypeVar("K", bound=SupportsDunderLT[Any])


def sortgroup_by(
    iterable: Iterable[T], key: Callable[[T], K]
) -> list[tuple[K, list[T]]]:
    return [(k, list(g)) for k, g in groupby(sorted(iterable, key=key), key)]


def format_string(text: str) -> str:
    if "pred color]" in text:
        return Pat.PRED_COLOR_PAT.sub(fmt_pred_color, text)
    if "[" in text and r"\[" not in text and "[/" not in text:
        return Pat.OPENING_BRACKET.sub(r"\[", text)

    return text


def wrap(text: Any, tag: str) -> str:
    return f"[{tag}]{format_string(str(text))}[/]"


def format_space(string: str) -> str:
    return Pat.CONSECUTIVE_SPACE.sub(r"[u]\g<0>[/]", string)


def format_new(string: str) -> str:
    string = re.sub("^\n+", lambda m: m[0].replace("\n", "⮠\n"), string)
    return wrap(format_space(string), BOLD_GREEN)


def format_old(string: str) -> str:
    string = re.sub("^\n|\n$", lambda m: m[0].replace("\n", "⮠ "), string)
    return wrap(string, f"s {BOLD_RED}")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    if change == "delete":
        return format_old(before)
    if change == "replace":
        return "".join(
            (format_old(a) + format_new(b)) if a != b else a
            for a, b in zip(before.partition("\n"), after.rpartition("\n"))
        )

    return wrap(before, "dim")


def make_difftext(
    before: str,
    after: str,
    junk: str = "".join(sorted((set(punctuation) - {"_", "-", ":"}) | {"\n"})),
) -> str:
    matcher = SequenceMatcher(lambda x: x in "", autojunk=False, a=before, b=after)
    ops = matcher.get_opcodes()
    to_remove_ids = [
        i
        for i, (op, a, b, c, d) in enumerate(ops)
        if 0 < i < len(ops) - 1
        and op == "equal"
        and b - a < 5
        and before[a:b].strip()
        and after[c:d].strip()
    ]
    for i in reversed(to_remove_ids):
        a, b = ops[i - 1], ops[i + 1]
        action = "replace"

        ops[i] = (action, a[1], b[2], a[3], b[4])

        del ops[i + 1]
        del ops[i - 1]

    return "".join(
        fmtdiff(code, before[a1:a2], after[b1:b2]) or "" for code, a1, a2, b1, b2 in ops
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


def get_theme() -> Theme | None:
    config_path = platformdirs.user_config_path("rich") / "config.ini"
    return Theme.read(str(config_path)) if config_path.exists() else None


class SafeConsole(Console):
    def render_str(self, text: str, **kwargs) -> Text:
        try:
            return super().render_str(text, **kwargs)
        except MarkupError:
            kwargs["markup"] = False
            return super().render_str(text, **kwargs)

    def print(self, *args, **kwargs):
        try:
            super().print(*args, **kwargs)
        except MarkupError:
            kwargs["markup"] = False
            super().print(*args, **kwargs)


def make_console(**kwargs) -> SafeConsole:
    kwargs.setdefault("theme", get_theme())
    kwargs.setdefault("force_terminal", True)
    kwargs.setdefault("force_interactive", False)
    kwargs.setdefault("emoji", True)
    return SafeConsole(**kwargs)


console = make_console()


class NewTable(Table):
    def __init__(self, *args, **kwargs) -> None:
        table_kwarg_names = set(Table.__init__.__code__.co_varnames)
        column_kwarg_names = kwargs.keys() - table_kwarg_names
        self.column_kwargs = {k: kwargs.pop(k) for k in column_kwarg_names}

        super().__init__(*args, **kwargs)

    def add_column(self, *args, **kwargs) -> None:
        for k, v in self.column_kwargs.items():
            kwargs.setdefault(k, v)

        self.show_header = True
        super().add_column(*args, **kwargs)

    def add_row(self, *args: RenderableType | None, **kwargs) -> None:
        rends = list(args)
        if (overflow := self.column_kwargs.get("overflow")) and (
            max_width := self.column_kwargs.get("max_width")
        ):
            rends = [(Text.from_markup(a) if isinstance(a, str) else a) for a in args]
            for r in rends:
                if isinstance(r, Text):
                    r.truncate(max_width, overflow=overflow)

        return super().add_row(*rends, **kwargs)

    def add_rows(self, rows: Iterable[Iterable[RenderableType]]) -> None:
        """Add multiple rows to the table."""
        for row in rows:
            self.add_row(*row)

    def add_dict_row(
        self,
        data: JSONDict,
        ignore_extra_fields: bool = False,
        sort_columns: bool = False,
        **kwargs,
    ) -> None:
        """Add a row to the table from a dictionary."""
        if not ignore_extra_fields:
            existing_cols = set(self.colnames)
            for field in (f for f in data if f not in existing_cols):
                self.add_column(field)
                self.columns[-1]._cells = [""] * self.row_count
                if sort_columns:
                    self.columns = sorted(self.columns, key=lambda c: c.header)

        values = [data.get(c, "") for c in self.colnames]
        self.add_row(
            *(
                (v if isinstance(v, (ConsoleRenderable, RichCast, str)) else str(v))
                for v in values
            ),
            **kwargs,
        )

    @property
    def colnames(self) -> list[str]:
        """Provide a mapping between columns names / ids and columns."""
        return [str(c.header) for c in self.columns]


def new_table(
    *headers: str, rows: Iterable[Iterable[RenderableType]] | None = None, **kwargs
) -> NewTable:
    if headers:
        kwargs.setdefault("header_style", "bold misty_rose1")
        kwargs.setdefault("show_header", True)
        kwargs.setdefault("box", box.SIMPLE_HEAVY)
    else:
        kwargs.setdefault("show_header", False)
        kwargs.setdefault("box", box.ROUNDED)

    kwargs.setdefault("show_edge", False)
    kwargs.setdefault("pad_edge", False)
    kwargs.setdefault("highlight", True)
    kwargs.setdefault("row_styles", ["white"])
    kwargs.setdefault("expand", False)
    kwargs.setdefault("title_justify", "left")
    kwargs.setdefault("style", "black")
    kwargs.setdefault("border_style", "black")

    table = NewTable(*headers, **kwargs)
    if rows:
        table.add_rows(rows)
    return table


def list_table(items: Iterable[RenderableType], **kwargs) -> NewTable:
    return new_table(rows=[[i] for i in items], **kwargs)


def _randint() -> int:
    return random.randint(50, 205)


def adjust_color_intensity(
    rgb_color: tuple[int, int, int], factor: float
) -> tuple[int, ...]:
    # Convert RGB to HSL
    h, _l, s = colorsys.rgb_to_hls(*[c / 255.0 for c in rgb_color])

    # Adjust the lightness (intensity) while keeping hue constant
    new_l = max(0, min(1, 0.5 * factor))

    # Convert back to RGB
    return tuple(int(c * 255) for c in colorsys.hls_to_rgb(h, new_l, s))


@lru_cache
def predictably_random_color(string: str, intensity: float | None = None) -> str:
    random.seed(string.strip())
    r, g, b = _randint(), _randint(), _randint()
    if intensity is not None:
        r, g, b = adjust_color_intensity((r, g, b), intensity)

    return f"#{r:02X}{g:02X}{b:02X}"


def _format_with_color(string: str, on: str | None = None) -> str:
    color = f"b {predictably_random_color(string)}"
    if on:
        color += f" on {on}"
    return wrap(string, color)


def split_with_color(text: str) -> str:
    return " ".join(
        _format_with_color(str(x)) for x in sorted(Pat.SPLIT_PAT.split(text))
    )


def format_with_color(items: str | Sequence[str]) -> str:
    if isinstance(items, str):
        items = [items]

    return " ".join(_format_with_color(str(x)) for x in items)


def format_with_color_on_black(items: str | Iterable[str]) -> str:
    if not isinstance(items, Iterable) or isinstance(items, str):
        items = sorted(Pat.SPLIT_PAT.split(str(items)))

    sep = wrap("a", "#000000 on #000000")
    return " ".join(
        sep + _format_with_color(str(item), on="#000000") + sep for item in items
    )


def fmt_pred_color(m: Match[str]) -> str:
    return f"{predictably_random_color(m.group(2))}]{m.group(2)}"


def simple_panel(
    content: RenderableType, vertical_align: VerticalAlignMethod | None = None, **kwargs
) -> Panel:
    kwargs.setdefault("title_align", "left")
    kwargs.setdefault("subtitle_align", "right")
    kwargs.setdefault("box", box.SIMPLE)
    kwargs.setdefault("expand", False)
    kwargs.setdefault("border_style", "red")
    if "title" in kwargs:
        kwargs["title"] = wrap(kwargs["title"], "b")

    if vertical_align:
        content = Align.center(content, vertical=vertical_align)
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
            Pat.HTML_PARAGRAPH.sub("", content),
            inline_code_theme="nord-darker",
            code_theme="nord-darker",
            justify=kwargs.pop("justify", "left"),
        ),
        **kwargs,
    )


def new_tree(
    values: Iterable[RenderableType] | None = None, title: str = "", **kwargs
) -> Tree:
    if values is None:
        values = []
    kwargs.setdefault("guide_style", predictably_random_color(title or str(values)))
    kwargs.setdefault("highlight", True)
    tree = Tree(title, **kwargs)

    for val in values:
        tree.add(val)
    return tree


def get_country(code: str) -> str:
    return format_with_color(code)


def progress_bar(
    size: float, width: float, end: float | None = None, inverse: bool = False
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


def timestamp2datetime(timestamp: str | float | None) -> datetime:
    if isinstance(timestamp, str):
        timestamp = re.sub(r"[.]\d+", "", timestamp.strip("'"))
        formats = [
            "%Y-%m-%d",
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


def timestamp2timestr(timestamp: str | float | None) -> str:
    return timestamp2datetime(timestamp).strftime("%T")


@lru_cache
def get_colors_and_periods() -> list[tuple[Color, int, int]]:
    from coloraide import Color

    return [
        (c.filter("contrast", 0.5), *p)
        for c, p in zip(
            Color("magenta").harmony("wheel", space="oklch", count=7),
            [
                (60, 1),  # seconds
                (60, 60),  # minutes
                (24, 60 * 60),  # hours
                (31, 24 * 60 * 60),  # days
                (12, 31 * 24 * 60 * 60),  # months
                (365, 12 * 30 * 24 * 60 * 60),  # years
            ],
        )
    ]


@lru_cache
def get_td_color(seconds: float) -> str:
    for color, max_factor, seconds_in_unit in get_colors_and_periods():
        if seconds <= seconds_in_unit * max_factor:
            unit_count = seconds // seconds_in_unit
            center = max_factor / 2
            factor = -((unit_count - center) / center / 1.5) + 1
            return (
                color.filter("brightness", factor)
                .clip()
                .convert("srgb")
                .to_string(hex=True)
            )

    raise AssertionError("Shouldn't get here")


def human_dt(timestamp: str | float) -> str:
    try:
        dt = timestamp2datetime(timestamp)
    except ValueError:
        return str(timestamp)

    human_dt = humanize.naturaltime(dt)

    color = get_td_color(abs((dt.now(tz=dt.tzinfo) - dt).total_seconds()))

    return f"[b {color}]{human_dt}[/]"


def diff_dt(timestamp: str | float, acc: int = 2) -> str:
    try:
        datetime = timestamp2datetime(timestamp)
    except ValueError:
        return str(timestamp)

    diff = datetime.timestamp() - time.time()
    fmted = " ".join(islice(fmt_time(int(diff)), acc))

    strtime = datetime.strftime("%F" if abs(diff) >= SECONDS_PER_DAY else "%T")

    return f"{wrap(fmted, BOLD_RED if diff < 0 else BOLD_GREEN)} {strtime}"


def syntax(*args: Any, **kwargs: Any) -> Syntax:
    kwargs.setdefault("theme", "paraiso-dark")
    kwargs.setdefault("background_color", "black")
    kwargs.setdefault("word_wrap", True)
    return Syntax(*args, **kwargs)


def sql_syntax(sql_string: str) -> Syntax:
    import sqlparse

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


class hashable_list(list):
    def __hash__(self) -> int:
        return hash(tuple(self))


class hashable_dict(dict):
    def __hash__(self) -> int:
        return hash(tuple(self.items()))


@multimethod
def to_hashable(value: Any) -> Any:
    return value


@to_hashable.register
def _(value: list[Any]) -> list[Any]:
    return hashable_list(map(to_hashable, value))


@to_hashable.register
def _(value: dict[str, Any]) -> dict[str, Any]:
    return hashable_dict({k: to_hashable(v) for k, v in value.items()})


def diff_serialize(value: Any) -> str:
    if value is None:
        return ""
    return '""' if value == "" else str(value)


@multimethod
def diff(before: str, after: str) -> str:
    return make_difftext(before, after, printable)


@diff.register
def _(before: Any, after: Any) -> Any:
    return diff(diff_serialize(before), diff_serialize(after))


@diff.register
def _(before: list[Any], after: list[Any]) -> Any:
    return list(starmap(diff, zip_longest(before, after)))


@diff.register
def _(before: list[str], after: list[str]) -> Any:
    before_set, after_set = dict.fromkeys(before), dict.fromkeys(after)
    common = [k for k in before_set if k in after_set]
    return [
        *list(starmap(diff, zip(common, common))),
        *[
            diff(before or "", after or "")
            for before, after in zip_longest(
                [k for k in before_set if k not in common],
                [k for k in after_set if k not in common],
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


def pretty_diff(before: Any, after: Any, **kwargs) -> Text:
    result = diff(to_hashable(before), to_hashable(after))
    if not isinstance(result, str):
        result = (
            pformat(result, indent=2, width=300, sort_dicts=False)
            .replace("'", "")
            .replace('"', "")
            .replace("\\\\", "\\")
        )

    return Text.from_markup(result, **kwargs)
