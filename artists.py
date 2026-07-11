"""The artist database: one entry per painter, stored in artists.json at the
library root, shared by everything that needs to know about a painter rather
than a painting.

Each entry holds canonical name, birth/death years, nationality, primary
movement, a single 60-word bio, and a Wikipedia title, plus an alias map that
folds spelling variants ("Theodoros Ralli" / "Theodoros Rallis") onto one
canonical name. Entries are fetched once per painter by a small text-only API
call and cached forever; the file is plain JSON and hand-editable - a value
you fix by hand is never overwritten (lookups only fill fields that are still
empty).

Consumers: the cataloguer auto-fills missing entries after each run, the
sorter names painter folders from the years, and the viewer shows the bio on
every work by that painter. Keeping artist-level facts here, once, is also
what lets the per-image records stay about the image.
"""

import json
import os
import re
import unicodedata
from pathlib import Path

ARTISTS_FILE = "artists.json"
ARTIST_MODEL = "claude-sonnet-5"  # facts must be right; a whole library's index costs ~a cent
ARTIST_CHUNK = 25

ARTIST_SYSTEM = """You maintain the painter index of one reference library: `names` are raw artist strings from its catalogue and `library_folders` are painter folders that already exist there. Return one entry per raw name via the identify_painters tool.

CANONICAL FORM. Merge spelling variants of the same painter onto one canonical name: two raw names for the same painter must return the identical canonical string. When an entry in library_folders clearly refers to the same painter, adopt the folder's spelling; otherwise use the spelling standard references (English Wikipedia) use. A bare surname whose painter is obvious from the other names or folders (e.g. "Krachkovsky" beside "Iosif Krachkovsky") gets the full canonical name.

YEARS. Give birth and death years only when you securely know this specific painter. For living painters set living true and died null. When you cannot securely identify the painter or their dates, return null years and confident false.

FACTS. nationality is one word or a short phrase ("Russian", "French-Algerian"). movement is the painter's primary school in a few words ("Peredvizhniki realism", "Orientalist academic painting"). wiki is the exact English Wikipedia article title, or "" when there is none or you are unsure.

BIO. bio is 60 words MAXIMUM: training, subjects, what distinguishes the hand. Dense and concrete, no filler, and do not repeat the birth/death years. When you cannot securely identify the painter, return "" for bio, nationality, movement and wiki rather than guessing. Never pad; never invent."""

ARTIST_TOOL = {
    "name": "identify_painters",
    "description": "Return one index entry per raw painter name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "painters": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "raw": {"type": "string", "description": "The input name, echoed exactly."},
                    "canonical": {"type": "string", "description": "Canonical name; identical for variants of one painter."},
                    "born": {"type": ["integer", "null"]},
                    "died": {"type": ["integer", "null"], "description": "null when living or unknown."},
                    "living": {"type": "boolean"},
                    "confident": {"type": "boolean", "description": "false when identity or years are a guess."},
                    "nationality": {"type": "string", "description": "One word or short phrase; '' if unsure."},
                    "movement": {"type": "string", "description": "Primary school in a few words; '' if unsure."},
                    "bio": {"type": "string", "description": "60 words max on training, subjects, hand; '' if the painter cannot be securely identified."},
                    "wiki": {"type": "string", "description": "Exact English Wikipedia article title; '' if none or unsure."},
                },
                "required": ["raw", "canonical", "born", "died", "living", "confident",
                             "nationality", "movement", "bio", "wiki"],
            }},
        },
        "required": ["painters"],
    },
}


def _load_json(path, default):
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path, obj):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def norm(name):
    """Matching key for a painter name: accents, case, punctuation ignored."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold().replace("-", " ")
    s = re.sub(r"[^\w\s]", "", s, flags=re.U)
    return re.sub(r"\s+", " ", s).strip()


_YEARS_RE = re.compile(r"^(.*\S)\s+(\d{4})\s*[-–—]\s*(\d{4}|present)$", re.I)


def split_folder_years(name):
    """'Edgar Payne 1878-1947' -> ('Edgar Payne', '1878-1947'); no years -> (name, None)."""
    m = _YEARS_RE.match(str(name).strip())
    if not m:
        return str(name).strip(), None
    return m.group(1), "%s-%s" % (m.group(2), m.group(3).lower())


def roster_years(entry):
    """The 'YYYY-YYYY' / 'YYYY-present' span for an entry, or None."""
    if not entry.get("confident") or not entry.get("born"):
        return None
    if entry.get("died"):
        return "%s-%s" % (entry["born"], entry["died"])
    if entry.get("living"):
        return "%s-present" % entry["born"]
    return None


def folder_hints(root):
    """Year-stripped names of existing folders, as spelling hints for lookups."""
    return sorted({split_folder_years(d.name)[0] for d in Path(root).rglob("*") if d.is_dir()})[:300]


def load_artists(lib_root):
    db = _load_json(Path(lib_root) / ARTISTS_FILE, {"artists": {}, "aliases": {}})
    for canon in db["artists"]:
        db["aliases"].setdefault(norm(canon), canon)
    return db


def _artist_call(names, hints):
    import anthropic
    client = anthropic.Anthropic()
    out = []
    for i in range(0, len(names), ARTIST_CHUNK):
        chunk = names[i:i + ARTIST_CHUNK]
        payload = json.dumps({"names": chunk, "library_folders": hints}, ensure_ascii=False)
        msg = client.messages.create(
            model=ARTIST_MODEL, max_tokens=8192, system=ARTIST_SYSTEM,
            tools=[ARTIST_TOOL], tool_choice={"type": "tool", "name": "identify_painters"},
            messages=[{"role": "user", "content": payload}],
        )
        for block in msg.content:
            if getattr(block, "type", None) == "tool_use":
                out.extend(block.input.get("painters", []))
    return out


def _entry_from(e):
    return {"born": e.get("born"), "died": e.get("died"),
            "living": bool(e.get("living")), "confident": bool(e.get("confident")),
            "nationality": str(e.get("nationality") or ""), "movement": str(e.get("movement") or ""),
            "bio": str(e.get("bio") or ""), "wiki": str(e.get("wiki") or "")}


def ensure_artists(lib_root, raw_names, hints):
    """Return the database covering every raw name, calling the API only for
    names it has never seen (plus old entries that predate the bio fields).
    Hand-edited values win: lookups only fill fields that are still empty.
    Returns None when a lookup is needed but no API key is available."""
    db = load_artists(lib_root)
    unknown = {n for n in raw_names if n and norm(n) not in db["aliases"]}
    stale = {c for c, e in db["artists"].items() if "bio" not in e}
    lookup = sorted(unknown | stale)
    if not lookup:
        return db
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n  %d painter(s) need a one-time artist-index lookup (canonical name," % len(lookup))
        print("  years, bio), which takes one tiny text-only API call.")
        print("  Set ANTHROPIC_API_KEY first, then run this again.")
        return None
    print("  Looking up %d painter(s) for the artist index (text-only, ~a cent)..." % len(lookup))
    got = {}
    for e in _artist_call(lookup, hints):
        if isinstance(e, dict) and e.get("raw"):
            got[e["raw"]] = e
    for raw in lookup:
        e = got.get(raw, {})
        canonical = str(e.get("canonical") or raw).strip() or raw
        new = _entry_from(e)
        cur = db["artists"].get(canonical)
        if cur is None:
            db["artists"][canonical] = new
        else:
            for k, v in new.items():
                if cur.get(k) in (None, "", False) and v not in (None, "", False):
                    cur[k] = v
            cur.setdefault("bio", new["bio"])  # mark old entries as enriched
        db["aliases"][norm(raw)] = canonical
        db["aliases"].setdefault(norm(canonical), canonical)
    _save_json(Path(lib_root) / ARTISTS_FILE, db)
    print("  Artist index saved to %s (hand-editable; your edits are kept)." % ARTISTS_FILE)
    return db
