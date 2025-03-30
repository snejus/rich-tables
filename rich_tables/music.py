from __future__ import annotations

import operator as op
from collections import defaultdict
from functools import lru_cache, partial
from typing import TYPE_CHECKING, Any, TypeVar

from rich import box
from rich.align import Align
from rich.console import ConsoleRenderable, Group

from .fields import FIELDS_MAP
from .utils import (
    DISPLAY_HEADER,
    NewTable,
    border_panel,
    new_table,
    predictably_random_color,
    simple_panel,
    sortgroup_by,
    wrap,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rich.panel import Panel
    from rich.table import Table

JSONDict = dict[str, Any]

TRACK_FIELDS = [
    "track",
    "track_alt",
    "length",
    "artist",
    "artists",
    "artwork_url",
    "title",
    "bpm",
    "last_played",
    "plays",
    "skips",
    "helicopta",
    "hidden",
    "lyrics",
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
}


new_table = partial(new_table, collapse_padding=True, expand=True, padding=0)


def get_header(key: str) -> str:
    return DISPLAY_HEADER.get(key, key)


@lru_cache(maxsize=128)
def get_val(track: JSONDict, field: str) -> Any:
    trackdict = dict(track)
    return FIELDS_MAP[field](trackdict[field]) if trackdict.get(field) else ""


def get_vals(
    fields: Iterable[str], tracks: Iterable[JSONDict]
) -> Iterable[Iterable[str]]:
    return [[get_val(tuple(t.items()), f) for f in fields] for t in tracks]


def tracks_table(tracks: list[JSONDict], fields: list[str], color: str) -> NewTable:
    return new_table(
        *map(get_header, fields),
        rows=get_vals(fields, tracks),
        border_style=color,
        padding=(0, 0, 0, 1),
    )


T = TypeVar("T")


def album_stats(tracks: list[JSONDict]) -> JSONDict:
    def agg(field: str, default: T) -> Iterable[T]:
        return ((x.get(field) or default) for x in tracks)

    stats: JSONDict = dict(
        bpm=round(sum(agg("bpm", 0)) / len(tracks)),
        rating=round(sum(agg("rating", 0)) / len(tracks), 2),
        plays=sum(agg("plays", 0)),
        skips=sum(agg("skips", 0)),
        mtime=max(agg("mtime", 0)),
        last_played=max(agg("last_played", 0)),
        tracktotal=(str(len(tracks)), str(tracks[0].get("tracktotal")) or "0"),
        comments="\n---\n---\n".join(set(agg("comments", ""))),
    )
    return stats


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
    name = album["album"]
    artist = album.get("albumartist") or album.get("artist")
    genre = album.get("genre") or ""
    released = album.get("released", "")
    title = (
        f"{name} by {artist}"
        if album["albumtypes"] != "single"
        else f"singles by {artist}"
    )
    return new_table(rows=[[format_title(title), format_title(released), genre]])


def album_info(tracks: list[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = sorted([f for f in tracks[0] if f not in TRACK_FIELDS])

    album = defaultdict(str, zip(fields, op.itemgetter(*fields)(first)))
    if not album["album"]:
        album.update(album="Singles", albumartist=first["artist"])
    album.update(**album_stats(tracks))
    add_colors(album)
    for field, _ in filter(op.truth, sorted(album.items())):
        album[field] = get_val(tuple(album.items()), field)
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
    # ignore the artist field if there is only one found
    if len(tracks) > 1 and len({t.get("artist") for t in tracks}) == 1:
        track_fields.remove("artist")

    # ignore empty fields
    track_fields = [
        f for f in track_fields if {t.get(f) for t in tracks} not in ({None}, {""})
    ]
    tracks = sorted(tracks, key=op.itemgetter("track", "artist", "title"))
    tracklist = tracks_table(tracks, track_fields, album["album_color"])

    last_track_index = tracks.index(
        next(
            iter(sorted(tracks, key=lambda t: t.get("last_played") or 0, reverse=True))
        )
    )
    tracklist.rows[last_track_index].style = "b white on #000000"
    tracklist.add_row(
        *[album.get(k) or "" for k in ["tracktotal", *track_fields[1:]]],
        style="d white on grey11",
    )

    comments = album.get("comments")
    return border_panel(
        Group(
            album["album_title"],
            Align.center(
                simple_panel(
                    comments, style="grey54", expand=True, vertical_align="middle"
                )
            )
            if comments
            else "",
            new_table(rows=[[album_info_table(album), tracklist]]),
        ),
        box=box.DOUBLE_EDGE,
        style=album["albumartist_color"],
        subtitle=f"[b white]{url}",
    )


def albums_table(all_tracks: list[JSONDict], **__: Any) -> Iterable[ConsoleRenderable]:
    def get_album(track: JSONDict) -> str:
        return track.get("album") or ""

    for track in all_tracks:
        if not track["album"] and "single" in track.get("albumtype", ""):
            track["album"] = "singles"
            track["albumartist"] = track["label"]

    for _, tracks in sortgroup_by(all_tracks, get_album):
        yield album_panel(list(tracks))
