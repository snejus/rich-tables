import itertools as it
import operator as op
import re
from collections import defaultdict
from functools import partial
from typing import Any, Callable, Dict, Iterable, List, Tuple

from ordered_set import OrderedSet
from rich import box
from rich.align import Align
from rich.console import ConsoleRenderable, Group
from rich.panel import Panel
from rich.table import Table

from .utils import (
    FIELDS_MAP,
    border_panel,
    new_table,
    predictably_random_color,
    simple_panel,
    wrap
)

JSONDict = Dict[str, Any]

TRACK_FIELDS = OrderedSet(
    ["track", "length", "artist", "title", "bpm", "last_played", "stats", "helicopta"]
)
ALBUM_IGNORE = TRACK_FIELDS | {
    "album_color",
    "albumartist_color",
    "album",
    "album_title",
    "comments",
    "genre",
    "tracktotal",
    "plays",
    "skips",
    "albumartist",
}


DISPLAY_HEADER: Dict[str, str] = {
    "track": "#",
    "bpm": "🚀",
    "stats": "",
    "last_played": "  🎶 ⏰",
    "mtime": "updated",
    "data_source": "source",
    "helicopta": ":helicopter:",
    "track_alt": ":cd:",
    "catalognum": "📖",
}

new_table = partial(new_table, collapse_padding=True, expand=True, padding=0)


def get_header(key: str) -> str:
    return DISPLAY_HEADER.get(key, key)


def get_def(obj: JSONDict, default: Any = "") -> Callable[[str], Any]:
    def get_value(key: str) -> Any:
        return obj.get(key) or default

    return get_value


def get_val(track: JSONDict, field: str) -> str:
    return FIELDS_MAP[field](track[field]) if track.get(field) else ""


def get_vals(
    fields: OrderedSet[str], tracks: Iterable[JSONDict]
) -> Iterable[Iterable[str]]:
    for track in tracks:
        if "skips" and "plays" in track:
            track["stats"] = track.pop("plays", ""), track.pop("skips", "")
        # track["track"] = track.pop("track_alt", None) or track["track"]

    return map(lambda t: list(map(lambda f: get_val(t, f), fields)), tracks)


def album_stats(tracks: List[JSONDict]) -> JSONDict:
    def agg(field: str, default=0) -> Iterable:
        return map(lambda x: x.get(field) or default, tracks)

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
    stats["stats"] = str(stats.get("plays") or ""), str(stats.get("skips") or "")
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


def album_title(album: JSONDict) -> str:
    name = re.sub(r"\].* - ", "]", album["album"])
    artist = album.get("albumartist") or album.get("artist")
    genre = album.get("genre") or ""
    return format_title(f"{name} by {artist}") + 10 * " " + genre


def album_info(tracks: List[JSONDict]) -> JSONDict:
    first = tracks[0]
    fields = set(first.keys()) - TRACK_FIELDS

    album = defaultdict(str, zip(fields, op.itemgetter(*fields)(first)))
    album.update(**album_stats(tracks))
    add_colors(album)
    for field, val in filter(op.truth, sorted(album.items())):
        album[field] = get_val(album, field)
    album["album_title"] = album_title(album)
    return album


def album_info_table(album: JSONDict) -> Table:
    def should_display(keyval: Tuple[str, Any]) -> bool:
        return keyval[1] and keyval[0] not in ALBUM_IGNORE

    items = filter(should_display, sorted(album.items()))
    table = new_table(rows=map(lambda x: (get_header(x[0]), x[1]), items))
    table.columns[0].style = "b " + album["album_color"]
    return table


def simple_tracks_table(tracks, color="white", fields=TRACK_FIELDS, sort=False):
    # type: (List[JSONDict], str, OrderedSet[str], bool) -> Table
    return new_table(
        rows=get_vals(
            fields,
            sorted(tracks, key=op.methodcaller("get", "track", "")) if sort else tracks,
        ),
        expand=False,
    )


def _tracks_table(tracks, color="white", fields=TRACK_FIELDS, sort=True):
    # type: (List[JSONDict], str, OrderedSet[str], bool) -> Table
    return new_table(
        *map(get_header, fields.intersection({*tracks[0].keys(), "stats"})),
        rows=get_vals(
            fields,
            sorted(tracks, key=op.methodcaller("get", "track", "")) if sort else tracks,
        ),
        border_style=color,
    )


def tracklist_summary(album: JSONDict, fields: List[str]) -> List[str]:
    fields[0] = "tracktotal"
    mapping = dict(zip(fields, map(lambda f: album.get(f, ""), fields)))
    return list(op.itemgetter(*fields)(mapping))


def track_fields(tracks: List[JSONDict]) -> OrderedSet[str]:
    """Ignore the artist field if there is only one found."""
    fields = TRACK_FIELDS.copy()
    if len(tracks) > 1 and len(set(map(lambda x: x.get("artist"), tracks))) == 1:
        fields.discard("artist")
    return fields


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
        fields = OrderedSet([*tracks[0].keys(), "stats"])
        fields.discard("albumtypes")

    color = predictably_random_color(str(len(tracks)))
    tracklist = simple_tracks_table(tracks, album["album_color"], fields)
    return border_panel(tracklist, title=title, style=color)


def detailed_album_panel(tracks: List[JSONDict]) -> Panel:
    album = album_info(tracks)

    t_fields = track_fields(tracks)
    tracklist = _tracks_table(tracks, album["album_color"], t_fields)

    _, track = max(map(op.itemgetter("last_played", "track"), tracks))
    if int(re.sub(r"\D", "", str(track).replace("A", "1"))) > 0:
        row_no = tracklist.columns[0]._cells.index(str(track))
        tracklist.rows[row_no].style = "b white on #000000"
        tracklist.add_row(
            *tracklist_summary(album, list(t_fields)), style="d white on grey11"
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


def albums_table(all_tracks: List[JSONDict]) -> ConsoleRenderable:
    def is_single(track: JSONDict) -> bool:
        album, albumtype = track.get("album"), track.get("albumtypes")
        return not album or albumtype == "single"

    def get_album(track: JSONDict) -> str:
        return track.get("album") or ""

    for track in filter(is_single, all_tracks):
        track["album"] = "singles"
        track["albumartist"] = track["label"]

    albums = []
    for album_name, tracks in it.groupby(all_tracks, get_album):
        albums.append(detailed_album_panel(list(tracks)))
    return Group(*albums)


def tracks_table(all_tracks: List[JSONDict]) -> ConsoleRenderable:
    ignore = {"plays", "skips"}
    fields = OrderedSet([*all_tracks[0].keys(), "stats"]).difference(ignore)

    return _tracks_table(all_tracks, "blue", fields, sort=False)
