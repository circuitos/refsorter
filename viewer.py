"""Build wiki.html, the self-contained browser viewer.

The page template lives in templates/wiki.html and is read when the viewer is
built; the standalone build inlines it into WIKI_TEMPLATE instead. wiki.html
must stay a single file that works over file:// with zero network
dependencies. It references images by relative path, so it is always written
into the library root - the one file that lives there rather than in
_database. The artist index (_database/artists.json) is injected alongside
the records so every card can show its painter's bio.
"""

import json
from pathlib import Path

from record_schema import MOVEMENT_INFO
from artists import ARTISTS_FILE, DB_DIR

WIKI_TEMPLATE = None  # the standalone build inlines templates/wiki.html here


def _template():
    if WIKI_TEMPLATE is not None:
        return WIKI_TEMPLATE
    return (Path(__file__).resolve().parent / "templates" / "wiki.html").read_text(encoding="utf-8")


def write_wiki(out_dir, catalog):
    records = list(catalog.values())
    artists_path = Path(out_dir) / DB_DIR / ARTISTS_FILE
    artists = {"artists": {}, "aliases": {}}
    if artists_path.exists():
        with open(artists_path, "r", encoding="utf-8") as f:
            artists = json.load(f)
    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    info_json = json.dumps(MOVEMENT_INFO, ensure_ascii=False).replace("</", "<\\/")
    artists_json = json.dumps(artists, ensure_ascii=False).replace("</", "<\\/")
    root_json = json.dumps(Path(out_dir).name or "Library", ensure_ascii=False)
    html = (_template().replace("__DATA__", data_json)
            .replace("__INFO__", info_json)
            .replace("__ARTISTS__", artists_json)
            .replace("__ROOT__", root_json)
            .replace("__COUNT__", str(len(records))))
    path = Path(out_dir) / "wiki.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
