from __future__ import annotations

import colorsys
import random
import re
from collections import UserDict
from collections.abc import Iterable, Sequence
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import groupby
from math import copysign
from re import Match
from typing import TYPE_CHECKING, Any, Callable, Protocol, SupportsFloat, TypeVar

import humanize
import platformdirs
from rich import box
from rich.align import Align, VerticalAlignMethod
from rich.bar import Bar
from rich.console import Console, RenderableType, RenderResult
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


class HashableDict(UserDict[str, Any]):
    def __hash__(self) -> int:
        return hash(tuple(self.data.items()))


BOLD_GREEN = "b green"
BOLD_RED = "b red"
DISPLAY_HEADER: dict[RenderableType, str] = {
    "track": "#",
    "bpm": "🚀",
    "last_played": ":timer_clock: ",
    "mtime": "updated",
    "data_source": "source",
    "helicopta": ":helicopter: ",
    "hidden": ":no_entry: ",
    "track_alt": ":cd: ",
    "catalognum": ":pen: ",
    "plays": "[b green]:play_button: [/]",
    "skips": "[b red]:stop_button: [/]",
    "albumtypes": "types",
}


class Pat:
    SPLIT_PAT = re.compile(r"[;,] ?")
    PRED_COLOR_PAT = re.compile(r"(pred color)\]([^\[]+)")
    HTML_PARAGRAPH = re.compile(r"</?p>")
    OPENING_BRACKET = re.compile(r"\[(?!http)")


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
    def render_str(self, text: str, **kwargs: Any) -> Text:
        try:
            return super().render_str(text, **kwargs)
        except MarkupError:
            kwargs["markup"] = False
            return super().render_str(text, **kwargs)

    def print(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().print(*args, **kwargs)
        except MarkupError:
            kwargs["markup"] = False
            super().print(*args, **kwargs)


def make_console(**kwargs: Any) -> SafeConsole:
    kwargs.setdefault("theme", get_theme())
    kwargs.setdefault("force_terminal", True)
    kwargs.setdefault("force_interactive", False)
    kwargs.setdefault("emoji", True)
    return SafeConsole(**kwargs)


console = make_console()


class NewTable(Table):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        table_kwarg_names = set(Table.__init__.__code__.co_varnames)
        column_kwarg_names = kwargs.keys() - table_kwarg_names
        self.column_kwargs = {k: kwargs.pop(k) for k in column_kwarg_names}

        super().__init__(*args, **kwargs)

    def __rich_console__(self, *args: Any, **kwargs: Any) -> RenderResult:
        for column in self.columns:
            if display_header := DISPLAY_HEADER.get(column.header):
                column.header = display_header

        return super().__rich_console__(*args, **kwargs)

    def add_column(self, *args: Any, **kwargs: Any) -> None:
        for k, v in self.column_kwargs.items():
            kwargs.setdefault(k, v)

        self.show_header = True
        super().add_column(*args, **kwargs)

    def add_row(self, *args: RenderableType | None, **kwargs: Any) -> None:
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
        data: JSONDict | HashableDict,
        ignore_extra_fields: bool = False,
        transform: Callable[..., RenderableType] = lambda v, _: v,
        **kwargs: Any,
    ) -> None:
        """Add a row to the table from a dictionary."""
        if not ignore_extra_fields:
            existing_cols = set(self.colnames)
            for field in (f for f in data if f not in existing_cols):
                self.add_column(field)
                self.columns[-1]._cells = [""] * self.row_count

        values = (transform(data.get(k), k) for k in self.colnames)

        self.add_row(*values, **kwargs)

    @property
    def colnames(self) -> list[str]:
        """Provide a mapping between columns names / ids and columns."""
        return [str(c.header) for c in self.columns]


def new_table(
    *headers: str, rows: Iterable[Iterable[RenderableType]] | None = None, **kwargs: Any
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


def list_table(items: Iterable[RenderableType], **kwargs: Any) -> NewTable:
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
    content: RenderableType,
    vertical_align: VerticalAlignMethod | None = None,
    **kwargs: Any,
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


def border_panel(content: RenderableType, **kwargs: Any) -> Panel:
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
    values: Iterable[RenderableType] | None = None, label: str = "", **kwargs: Any
) -> Tree:
    values_list = list(values) if values else []
    kwargs.setdefault("highlight", True)
    if label:
        label = wrap(label, "b")
    tree = Tree(label, **kwargs)

    for val in values_list:
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
            with suppress(ValueError):
                return datetime.strptime(timestamp, fmt).replace(tzinfo=timezone.utc)
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
