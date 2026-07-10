"""Build wiki.html, the self-contained browser viewer.

The page template lives in templates/wiki.html and is read when the viewer is
built; the standalone build inlines it into WIKI_TEMPLATE instead. wiki.html
must stay a single file that works over file:// with zero network
dependencies. It references images by relative path, so it is always written
into the library root.
"""

import json
from pathlib import Path

from record_schema import MOVEMENT_INFO

WIKI_TEMPLATE = None  # the standalone build inlines templates/wiki.html here


def _template():
    if WIKI_TEMPLATE is not None:
        return WIKI_TEMPLATE
    return (Path(__file__).resolve().parent / "templates" / "wiki.html").read_text(encoding="utf-8")


def write_wiki(out_dir, catalog):
    records = list(catalog.values())
    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    info_json = json.dumps(MOVEMENT_INFO, ensure_ascii=False).replace("</", "<\\/")
    html = (_template().replace("__DATA__", data_json)
            .replace("__INFO__", info_json)
            .replace("__COUNT__", str(len(records))))
    path = Path(out_dir) / "wiki.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
