from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from operator import attrgetter
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from rich.bar import Bar
from rich.columns import Columns
from typing_extensions import Literal, NotRequired, TypedDict

from .fields import get_val
from .utils import border_panel, new_table, sortgroup_by, wrap

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rich.console import RenderableType
JSONDict = dict[str, Any]

SYMBOL_BY_STATUS = {
    "needsAction": "[b grey3] ? [/]",
    "accepted": "[b green]   [/]",
    "declined": "[b red] ✖ [/]",
    "tentative": "[b yellow] ? [/]",
}


class Datetime(TypedDict):
    dateTime: NotRequired[str]
    date: NotRequired[str]
    timeZone: NotRequired[str]


@dataclass
class Period:
    color: str
    desc: str
    end: datetime
    summary: str
    start: datetime
    status_symbol: str
    fmt: str

    @classmethod
    def make(cls, **kwargs: Any) -> Period:
        kwargs["fmt"] = (
            "dim strike"
            if kwargs["end"] < datetime.now(tz=kwargs["end"].tzinfo)
            else ""
        )
        kwargs["desc"] = (kwargs["desc"] or "").strip()
        return cls(**kwargs)

    @property
    def start_day(self) -> str:
        return self.start.strftime("%d %A")

    @property
    def start_year_month(self) -> str:
        return self.start.strftime("%Y %B")

    @property
    def start_time(self) -> str:
        return wrap(self.start.strftime("%H:%M"), "white")

    @property
    def end_time(self) -> str:
        return wrap(self.end.strftime("%H:%M"), "white")

    @property
    def bar(self) -> Bar:
        if self.start.hour == self.end.hour == 0:
            begin, end = 0, 86400
        else:
            midnight_ts = self.start.replace(hour=0).timestamp()
            begin = int(self.start.timestamp() - midnight_ts)
            end = int(self.end.timestamp() - midnight_ts)

        return Bar(86400, begin, end, color=self.color)

    @property
    def name(self) -> RenderableType:
        title = self.status_symbol + wrap(self.summary, f"b {self.color} {self.fmt}")
        return border_panel(get_val(self, "desc"), title=title) if self.desc else title


@dataclass
class Event:
    backgroundColor: str
    calendar: str
    desc: str
    end: datetime
    summary: str
    status: Literal["accepted", "needsAction", "declined", "tentative"]
    start: datetime

    @classmethod
    def make(cls, start: Datetime, end: Datetime, summary: str, **kwargs: Any) -> Event:
        return cls(
            start=cls.get_datetime(start),
            end=cls.get_datetime(end),
            summary=summary or "busy",
            **kwargs,
        )

    @property
    def status_symbol(self) -> str:
        return SYMBOL_BY_STATUS[self.status]

    @staticmethod
    def get_datetime(date_obj: Datetime) -> datetime:
        date = date_obj.get("dateTime") or date_obj.get("date") or ""
        dt = datetime.fromisoformat(date.strip("Z"))
        return dt.replace(tzinfo=ZoneInfo(date_obj.get("timeZone") or "UTC"))

    def get_periods(self) -> list[Period]:
        diff = self.end - self.start
        h_after_midnight = (24 * diff.days + (diff.seconds // 3600)) - (
            24 - self.start.hour
        )

        end = (self.start + timedelta(days=1)).replace(hour=0, minute=0, second=0)

        def eod(day_offset: int) -> datetime:
            return (self.start + timedelta(days=day_offset)).replace(
                hour=23, minute=59, second=59
            )

        def midnight(day_offset: int) -> datetime:
            return (self.start + timedelta(days=day_offset)).replace(
                hour=0, minute=0, second=0
            )

        days_count = h_after_midnight // 24 + 1
        periods = []
        for start, end in zip(
            [self.start, *map(midnight, range(1, days_count + 1))],
            [*map(eod, range(days_count)), self.end],
        ):
            periods.append(
                Period.make(
                    status_symbol=self.status_symbol,
                    color=self.backgroundColor,
                    start=start,
                    end=end,
                    desc=self.desc,
                    summary=self.summary,
                )
            )
        return periods


def get_legend(events: list[Event]) -> RenderableType:
    """Return a renderable with a list of calendars and their colors."""
    calendar_and_color = sorted({(e.calendar, e.backgroundColor) for e in events})
    colored_calendars = (
        wrap(f" {c} ", f"b black on {clr}") for c, clr in calendar_and_color
    )
    return Columns(
        colored_calendars,
        title="Calendars",
        expand=True,
        equal=True,
        align="center",
    )


def get_months(events: list[Event]) -> Iterable[RenderableType]:
    all_periods = [p for e in events for p in e.get_periods()]

    headers = "name", "start_time", "end_time", "bar"
    get_values = attrgetter(*headers)
    for year_and_month, month_periods in sortgroup_by(
        all_periods, lambda x: x.start_year_month
    ):
        table = new_table(*headers, highlight=True, padding=0, show_header=False)
        for day, day_periods in sortgroup_by(month_periods, lambda x: x.start_day):
            table.add_row(wrap(day, "b i"))
            for period in day_periods:
                values = get_values(period)
                if "Week " in period.summary:
                    table.add_row("")
                    table.add_row(*values, style=f"{period.color} on grey3")
                else:
                    table.add_row(*values)
            table.add_row("")
        yield border_panel(table, title=year_and_month)


def get_table(events_data: list[JSONDict], **__: Any) -> Iterable[RenderableType]:
    events = [Event.make(**e) for e in events_data]
    yield get_legend(events)
    yield from get_months(events)
