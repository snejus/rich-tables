from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, Iterable

from rich.bar import Bar
from rich.columns import Columns

from .fields import get_val
from .utils import (
    border_panel,
    group_by,
    new_table,
    predictably_random_color,
    wrap,
)

if TYPE_CHECKING:
    from rich.console import RenderableType

JSONDict = Dict[str, Any]


def get_start_end(start: datetime, end: datetime) -> tuple[int, int]:
    if start.hour == end.hour == 0:
        return 0, 86400
    day_start_ts = start.replace(hour=0).timestamp()
    return int(start.timestamp() - day_start_ts), int(end.timestamp() - day_start_ts)


def get_table(events: list[JSONDict], **__) -> Iterable[RenderableType]:
    status_map = {
        "needsAction": "[b grey3] ? [/]",
        "accepted": "[b green] ✔ [/]",
        "declined": "[b red] ✖ [/]",
        "tentative": "[b yellow] ? [/]",
    }

    cal_to_color = {e["calendar"]: e["backgroundColor"] for e in events}
    if len(cal_to_color) > 1:
        color_key = "calendar"
        color_id_to_color = cal_to_color
    else:
        color_key = "colorId"
        color_id_to_color = {
            e[color_key]: predictably_random_color(e[color_key]) for e in events
        }
    for e in events:
        e["color"] = color_id_to_color[e[color_key]]
    cal_fmted = [wrap(f" {c} ", f"b black on {clr}") for c, clr in cal_to_color.items()]
    yield Columns(cal_fmted, expand=True, equal=False, align="center")

    new_events: list[JSONDict] = []
    for event in events:
        start_iso, end_iso = event["start"], event["end"]
        orig_start = datetime.fromisoformat(
            (start_iso.get("dateTime") or start_iso.get("date")).strip("Z")
        )
        orig_end = datetime.fromisoformat(
            (end_iso.get("dateTime") or end_iso.get("date")).strip("Z")
        )
        h_after_midnight = (
            24 * (orig_end - orig_start).days
            + ((orig_end - orig_start).seconds // 3600)
        ) - (24 - orig_start.hour)

        end = (orig_start + timedelta(days=1)).replace(hour=0, minute=0, second=0)

        def eod(day_offset: int) -> datetime:
            return (orig_start + timedelta(days=day_offset)).replace(
                hour=23, minute=59, second=59
            )

        def midnight(day_offset: int) -> datetime:
            return (orig_start + timedelta(days=day_offset)).replace(
                hour=0, minute=0, second=0
            )

        days_count = h_after_midnight // 24 + 1
        for start, end in zip(
            [orig_start, *map(midnight, range(1, days_count + 1))],
            [*map(eod, range(days_count)), orig_end],
        ):
            color = (
                "grey7" if end.replace(tzinfo=None) < datetime.now() else event["color"]
            )
            title = status_map[event["status"]] + wrap(
                event["summary"] or "busy", f"b {color}"
            )
            new_events.append({
                **event,
                "color": color,
                "name": (
                    border_panel(get_val(event, "desc"), title=title)
                    if event["desc"]
                    else title
                ),
                "start": start,
                "start_day": start.strftime("%d %a"),
                "start_time": wrap(start.strftime("%H:%M"), "white"),
                "end_time": wrap(end.strftime("%H:%M"), "white"),
                "desc": (border_panel(get_val(event, "desc")) if event["desc"] else ""),
                "bar": Bar(86400, *get_start_end(start, end), color=color),
                "summary": event["summary"] or "",
            })

    keys = "name", "start_time", "end_time", "bar"
    month_events: Iterable[JSONDict]
    for year_and_month, month_events in group_by(
        new_events, lambda x: x["start"].strftime("%Y %B")
    ):
        table = new_table(*keys, highlight=False, padding=0, show_header=False)
        for day, day_events in group_by(
            month_events, lambda x: x.get("start_day") or ""
        ):
            table.add_row(wrap(day, "b i"))
            for event in day_events:
                if "Week " in event["summary"]:
                    table.add_row("")
                    table.add_dict_item(event, style=event["color"] + " on grey7")
                else:
                    table.add_dict_item(event)
            table.add_row("")
        yield border_panel(table, title=year_and_month)
