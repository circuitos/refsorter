"""Record repair pipeline. clean_record runs on every record, both when
merging batch results and when loading an existing catalog, so old data is
auto-repaired on load.

Order inside clean_record matters: _strip_leaks, then coerce_tags, then
normalize_movement, then recompute needs_review.
"""

import json

from record_schema import MOVEMENT_CANON, RECORD_TOOL

_MOVEMENT_RULES = [
    ("contemporary", "Contemporary"), ("post-soviet", "Contemporary"),
    ("socialist", "Socialist Realism"),
    ("shin-hanga", "Shin-hanga"), ("shin hanga", "Shin-hanga"),
    ("ukiyo", "Ukiyo-e"),
    ("post-impression", "Post-Impressionism"),
    ("impressioni", "Impressionism"),
    ("symbolis", "Symbolism"), ("tonalis", "Tonalism"),
    ("surreal", "Surrealism"), ("cubis", "Cubism"), ("fauv", "Fauvism"),
    ("expressionis", "Expressionism"), ("futuris", "Futurism"),
    ("abstract", "Abstract art"), ("art nouveau", "Art Nouveau"),
    ("naive", "Naive art"), ("na\u00efve", "Naive art"),
    ("realis", "Realism"),
    ("romantic", "Romanticism"),
    ("neoclassic", "Neoclassicism"), ("academic", "Academic art"),
    ("baroque", "Baroque"), ("rococo", "Rococo"),
    ("manneris", "Mannerism"), ("renaissance", "Renaissance"),
    ("gothic", "Medieval & Gothic"), ("medieval", "Medieval & Gothic"),
]


def normalize_movement(raw):
    """Map a free-text movement string onto the canonical list. Returns (canon, detail)."""
    s = (raw or "").strip()
    if not s:
        return "Other", ""
    if s in MOVEMENT_CANON:
        return s, ""
    low = s.lower()
    for needle, canon in _MOVEMENT_RULES:
        if needle in low:
            return canon, s
    return "Other", s


def coerce_tags(t):
    """The model sometimes returns tags as one comma-joined string; always store a list."""
    if isinstance(t, list):
        return [str(x).strip() for x in t if str(x).strip()]
    if t is None:
        return []
    s = str(t).strip().strip("[]")
    return [p.strip().strip("'\"") for p in s.split(",") if p.strip().strip("'\"")]


_LEAK = None  # compiled lazily below


def _leak_re():
    global _LEAK
    if _LEAK is None:
        import re
        _LEAK = re.compile(r'</[a-zA-Z_]+>|<parameter\b|</?antml', re.I)
    return _LEAK


def _strip_leaks(rec):
    """The model occasionally writes tool-call syntax as literal text inside a field,
    swallowing the following fields (e.g. context ends with '</context> <parameter
    name="tags">[...]'). Cut each string field at the first leak and recover any
    swallowed parameter values into their rightful (empty) fields."""
    import re
    param_re = re.compile(r'<parameter\s+name="([a-zA-Z_]+)">\s*(.*?)(?=<parameter\s+name="|</parameter>|$)', re.S)
    for field in list(rec.keys()):
        v = rec.get(field)
        if not isinstance(v, str):
            continue
        m = _leak_re().search(v)
        if not m:
            continue
        tail = v[m.start():]
        rec[field] = v[:m.start()].rstrip()
        for name, raw in param_re.findall(tail):
            if name not in RECORD_TOOL["input_schema"]["properties"]:
                continue
            raw = _leak_re().sub("", raw).strip()
            if not raw:
                continue
            cur = rec.get(name)
            if cur in (None, "", []):
                if name == "tags":
                    try:
                        rec[name] = json.loads(raw)
                    except Exception:
                        rec[name] = raw
                elif name == "needs_review":
                    rec[name] = raw.strip().lower() == "true"
                else:
                    rec[name] = raw
    return rec


def clean_record(rec):
    """Normalise one record in place: leak repair, tags, movement/detail split, review flag."""
    _strip_leaks(rec)
    rec["tags"] = coerce_tags(rec.get("tags"))
    canon, detail = normalize_movement(rec.get("movement"))
    prior_detail = (rec.get("movement_detail") or "").strip()
    rec["movement"] = canon
    rec["movement_detail"] = prior_detail or detail
    conf = rec.get("artist_confidence")
    rec["needs_review"] = bool(
        conf in ("medium", "low", "unknown")
        or rec.get("attribution_source") == "unknown"
        or not rec.get("artist")
    )
    return rec
