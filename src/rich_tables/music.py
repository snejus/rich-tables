import itertools as it
import operator as op
import re
from collections import defaultdict
from functools import lru_cache, partial
from typing import Any, Callable, Dict, Iterable, List, Tuple

from rich import box
from rich.align import Align
from rich.console import ConsoleRenderable, Group
from rich.panel import Panel
from rich.table import Table

from rich_tables.utils import (
    DISPLAY_HEADER,
    FIELDS_MAP,
    border_panel,
    new_table,
    predictably_random_color,
    simple_panel,
    wrap,
)

JSONDict = Dict[str, Any]

TRACK_FIELDS = [
    "track",
    "length",
    "artist",
    "title",
    "bpm",
    "last_played",
    "plays",
    "skips",
    "helicopta",
    "hidden",
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


def get_def(obj: JSONDict, default: Any = "") -> Callable[[str], Any]:
    def get_value(key: str) -> Any:
        return obj.get(key) or default

    return get_value


@lru_cache(maxsize=128)
def get_val(track: JSONDict, field: str) -> Any:
    trackdict = dict(track)
    return FIELDS_MAP[field](trackdict[field]) if trackdict.get(field) else ""


def get_vals(
    fields: Iterable[str], tracks: Iterable[JSONDict]
) -> Iterable[Iterable[str]]:
    return [[get_val(tuple(t.items()), f) for f in fields] for t in tracks]


def simple_tracks_table(tracks, fields, color, sort):
    # type: (List[JSONDict], Iterable[str], str, bool) -> Table
    return new_table(
        rows=get_vals(
            fields,
            sorted(tracks, key=op.methodcaller("get", "track", "")) if sort else tracks,
        ),
        expand=False,
    )


def _tracks_table(tracks, fields, color, sort):
    # type: (List[JSONDict], Iterable[str], str, bool) -> Table
    return new_table(
        *map(get_header, fields),
        rows=get_vals(
            fields,
            sorted(tracks, key=op.methodcaller("get", "track", "")) if sort else tracks,
        ),
        border_style=color,
        padding=(0, 0, 0, 1),
    )


def album_stats(tracks: List[JSONDict]) -> JSONDict:
    def agg(field: str, default: int = 0) -> Iterable[int]:
        return ((x.get(field) or default) for x in tracks)

    stats: JSONDict = dict(
        bpm=round(sum(agg("bpm")) / len(tracks)),
        rating=round(sum(agg("rating")) / len(tracks), 2),
        plays=sum(agg("plays")),
        skips=sum(agg("skips")),
        mtime=max(agg("mtime")),
        last_played=max(agg("last_played")),
        tracktotal=(str(len(tracks)), str(tracks[0].get("tracktotal")) or str(0)),
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
    return new_table(
        rows=[[format_title(f"{name} by {artist}"), format_title(released), genre]]
    )


def album_info(tracks: List[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = sorted([f for f in tracks[0] if f not in TRACK_FIELDS])

    album = defaultdict(str, zip(fields, op.itemgetter(*fields)(first)))
    album.update(**album_stats(tracks))
    add_colors(album)
    for field, val in filter(op.truth, sorted(album.items())):
        album[field] = get_val(tuple(album.items()), field)
    album["album_title"] = album_title(album)
    return album


def album_info_table(album: JSONDict) -> Table:
    def should_display(keyval: Tuple[str, Any]) -> bool:
        return keyval[1] and keyval[0] not in ALBUM_IGNORE

    items = filter(should_display, sorted(album.items()))
    table = new_table(rows=map(lambda x: (get_header(x[0]), x[1]), items))
    table.columns[0].style = "b " + album["album_color"]
    return table


def simple_album_panel(tracks: List[JSONDict]) -> Panel:
    album = album_info(tracks)

    get = album.get

    albumtype = get_val(album, "albumtypes")
    title = ""
    name = get("album")
    if name:
        label = get("label")
        title = format_title(
            (f"{label}: " if label else "")
            + " by ".join(filter(op.truth, [name, get("albumartist") or ""]))
            + f" ({albumtype})"
        )
        fields = TRACK_FIELDS
    else:
        fields = dict.fromkeys(k for k in tracks[0] if k != "albumtypes")

    color = predictably_random_color(str(len(tracks)))
    tracklist = simple_tracks_table(tracks, fields, album["album_color"], sort=False)
    return border_panel(tracklist, title=title, style=color)


def detailed_album_panel(tracks: List[JSONDict]) -> Panel:
    album = album_info(tracks)

    # ignore the artist field if there is only one found
    track_fields = [
        t
        for t in TRACK_FIELDS
        if len(tracks) > 1 or len(set(map(lambda x: x.get("artist"), tracks))) == 1
    ]
    tracklist = _tracks_table(tracks, track_fields, album["album_color"], sort=True)

    _, track = max(map(op.itemgetter("last_played", "track"), tracks))
    if int(re.sub(r"\D", "", str(track).replace("A", "1"))) > 0:
        row_no = tracklist.columns[0]._cells.index(str(track))
        tracklist.rows[row_no].style = "b white on #000000"
        tracklist.add_row(
            *[album.get(k) or "" for k in ["tracktotal", *track_fields[1:]]],
            style="d white on grey11",
        )

    comments = album.get("comments")
    return border_panel(
        Group(
            album["album_title"],
            Align.center(
                simple_panel(comments, style="grey54", expand=True, align="center")
            )
            if comments
            else "",
            new_table(rows=[[album_info_table(album), tracklist]]),
        ),
        box=box.DOUBLE_EDGE,
        style=album["albumartist_color"],
    )


def albums_table(all_tracks: List[JSONDict]) -> Iterable[ConsoleRenderable]:
    def get_album(track: JSONDict) -> str:
        return track.get("album") or ""

    for track in all_tracks:
        if not track["album"] and "single" in track.get("albumtype", ""):
            track["album"] = "singles"
            track["albumartist"] = track["label"]

    for album_name, tracks in it.groupby(sorted(all_tracks, key=get_album), get_album):
        yield detailed_album_panel(list(tracks))
