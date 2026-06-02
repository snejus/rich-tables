from __future__ import annotations

import operator as op
from collections import defaultdict
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar

from rich import box
from rich.align import Align
from rich.console import ConsoleRenderable, Group, NewLine, RenderableType

from .fields import get_val
from .generic import flexitable
from .utils import (
    DISPLAY_HEADER,
    NewTable,
    border_panel,
    format_with_color_on_black,
    new_table,
    predictably_random_color,
    simple_panel,
    sortgroup_by,
    to_hashable,
    wrap,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rich.panel import Panel
    from rich.table import Table

JSONDict = dict[str, Any]

MOST_RECENTLY_PLAYED_TRACK_STYLE = "b white on #000000"
TRACK_SORT_FIELDS = ["disc", "track", "artists", "title"]
TRACK_FIELDS = [
    "track",
    "track_alt",
    "length",
    "artists",
    "artwork_url",
    "title",
    "bpm",
    "last_played",
    "plays",
    "skips",
    "helicopta",
    "lyrics",
    "wait_per_play",
]
ALBUM_IGNORE = set(TRACK_FIELDS) | {
    "album_color",
    "albumartist_color",
    "album",
    "album_title",
    "comments",
    "genre",
    "tracktotal",
    "albumartist",
    "disc",
}


new_table = partial(new_table, collapse_padding=True, expand=True, padding=0)


def get_header(key: str) -> str:
    return DISPLAY_HEADER.get(key, key)


def tracks_table(
    tracks: list[JSONDict], fields: list[str], album: JSONDict
) -> NewTable:
    table = new_table(*fields, border_style=album["album_color"], padding=(0, 0, 0, 1))
    most_recently_played_track = max(tracks, key=lambda t: t.get("last_played", 0))
    disc_and_disc_tracks = sortgroup_by(tracks, lambda t: t["disc"])
    single_disc = len(disc_and_disc_tracks) == 1
    for disc, disc_tracks in disc_and_disc_tracks:
        if not single_disc:
            table.add_row(format_with_color_on_black(f"Disc {disc}"))
        for track in disc_tracks:
            table.add_dict_row(
                track,
                transform=flexitable,
                ignore_extra_fields=True,
                style=(
                    MOST_RECENTLY_PLAYED_TRACK_STYLE
                    if track == most_recently_played_track
                    else None
                ),
            )
        last_disc = disc_and_disc_tracks[-1][0]
        if not single_disc and disc != last_disc:
            table.add_section()

    album_totals = [album.get({"track": "tracktotal"}.get(k, k)) or "" for k in fields]
    table.add_row(
        *((format_with_color_on_black(at) if at else at) for at in album_totals),
        style="d white",
    )

    return table


T = TypeVar("T")


def album_stats(tracks: list[JSONDict]) -> JSONDict:
    def agg(field: str, default: T) -> Iterable[T]:
        return ((x.get(field) or default) for x in tracks)

    tracktotal_by_disc = {i["disc"]: i["tracktotal"] for i in tracks}
    total_tracktotal = sum(tracktotal_by_disc.values())
    return dict(
        bpm=round(sum(agg("bpm", 0)) / len(tracks)),
        rating=round(sum(agg("rating", 0)) / len(tracks), 2),
        plays=sum(agg("plays", 0)),
        skips=sum(agg("skips", 0)),
        mtime=max(agg("mtime", 0)),
        last_played=max(agg("last_played", 0)),
        tracktotal=(str(len(tracks)), total_tracktotal),
        comments="\n---\n---\n".join(set(agg("comments", ""))) or None,
    )


def add_colors(album: JSONDict) -> None:
    for field in "album", "albumartist":
        val = (album.get(field) or "").replace("Various Artists", "VA")
        color = predictably_random_color(val)
        album[f"{field}_color"] = color
        val = album.get(field)
        album[field] = wrap(val, f"b i {color}") if val else ""


def format_title(title: str) -> str:
    return wrap(f"  {title}  ", "i white on grey3")


def album_title(album: JSONDict) -> Table:
    artist = album.get("albumartist") or album.get("artist")
    title = " by ".join(filter(None, (album["album"], artist)))
    return new_table(
        rows=[
            [
                format_title(title),
                format_title(album.get("released", "")),
                album.get("genre") or "",
            ]
        ]
    )


def album_info(tracks: list[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = sorted([f for f in tracks[0] if f not in TRACK_FIELDS])

    album = defaultdict(str, zip(fields, op.itemgetter(*fields)(first)))
    if not album["album"]:
        album.update(album="Singles", albumartist="")
    album.update(**album_stats(tracks))
    add_colors(album)
    for field, _ in filter(op.truth, sorted(album.items())):
        album[field] = get_val(album, field)
    album["album_title"] = album_title(album)
    return album


def album_info_table(album: JSONDict) -> Table:
    def should_display(keyval: tuple[str, Any]) -> bool:
        return keyval[1] and keyval[0] not in ALBUM_IGNORE

    items = filter(should_display, sorted(album.items()))
    table = new_table(rows=((get_header(x[0]), x[1]) for x in items))
    table.columns[0].style = "b " + album["album_color"]
    return table


def album_panel(tracks: list[JSONDict]) -> Panel:
    album = album_info(tracks)
    url = album.pop("url", "")

    track_fields = list(TRACK_FIELDS)
    tracks = sorted(tracks, key=op.itemgetter(*TRACK_SORT_FIELDS))
    # ignore the artist field if there is only one found
    if len(tracks) > 1 and len({tuple(t.get("artists", [])) for t in tracks}) == 1:
        track_fields.remove("artists")

    # ignore empty fields
    track_fields = [f for f in track_fields if any(t.get(f) for t in tracks)]

    vertical_parts: list[RenderableType] = [album["album_title"]]
    if comments := album.get("comments"):
        comments_table = Align.center(
            simple_panel(comments, style="grey54", expand=True, vertical_align="middle")
        )
        vertical_parts.append(comments_table)
    else:
        vertical_parts.append(NewLine())
    vertical_parts.append(
        new_table(
            rows=[[album_info_table(album), tracks_table(tracks, track_fields, album)]],
        )
    )

    return border_panel(
        Group(*vertical_parts),
        box=box.DOUBLE_EDGE,
        style=album["albumartist_color"],
        expand=True,
        subtitle=f"[b white]{url}",
    )


def albums_table(all_tracks: list[JSONDict], **__: Any) -> Iterable[ConsoleRenderable]:
    def get_album(track: JSONDict) -> str:
        return track.get("album") or ""

    for track in all_tracks:
        if not track["album"] and "single" in track.get("albumtype", ""):
            track["album"] = "singles"
            track["albumartist"] = track["label"]

    for _, tracks in sortgroup_by(to_hashable(all_tracks), get_album):
        yield album_panel(list(tracks))
