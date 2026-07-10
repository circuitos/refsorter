#!/usr/bin/env python3
"""
catalog_refs.py - Contextualise a folder of painter reference images.

Just run it. It will ask you a couple of plain questions:

    python catalog_refs.py

Option 1 estimates the cost for free (no API key, no charge). Options 2 and 3
do the real cataloguing and need an Anthropic API key set on your machine.

Nothing is ever moved or renamed. Results are written next to your library as
catalog.json (the master file), catalog.csv (browsable), and review_queue.csv
(only the items worth a human double-check).
"""

import base64
import csv
import io
import json
import hashlib
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None  # these are your own files; lift Pillow's safety cap

# --------------------------------------------------------------------------- settings

# Your reference library. Press Enter at the prompt to accept this, or type another path.
DEFAULT_ROOT = r"F:\Dropbox\Dropbox\! REF\! PAINTERS"

# Current BATCH prices per million tokens (standard rate already halved for batch),
# checked 2026-07-10. Sonnet 5 is at introductory pricing through 2026-08-31.
# If you run this later, verify at https://www.claude.com/pricing and update these.
MODELS = {
    "1": {"id": "claude-sonnet-5",  "label": "Sonnet 5  (better attribution + context)", "in": 1.00, "out": 5.00},
    "2": {"id": "claude-haiku-4-5", "label": "Haiku 4.5 (cheaper, a bit blunter)",       "in": 0.50, "out": 2.50},
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
MAX_DIM = 1024            # longest edge in px before sending
JPEG_QUALITY = 85
CHUNK_SIZE = 1000         # requests per batch
MAX_BATCH_BYTES = 200 * 1024 * 1024
POLL_SECONDS = 20
OVERHEAD_IN = 900         # rough per-image input overhead (system + tool schema + text)
EST_OUT = 420             # rough per-image output tokens with the 60-word caps

STATE_FILE = ".catalog_state.json"
CATALOG_FILE = "catalog.json"
CATALOG_CSV = "catalog.csv"
REVIEW_CSV = "review_queue.csv"

CSV_COLUMNS = [
    "path", "artist", "artist_confidence", "attribution_source", "title",
    "title_confidence", "date_or_period", "movement", "movement_detail", "medium",
    "subject", "palette", "composition_notes", "context", "tags", "needs_review", "notes",
]

# Imported below the settings on purpose: make_standalone.py splices each
# module's source in at its import line, keeping the config at the top.
from record_schema import SYSTEM, RECORD_TOOL
from cleaning import clean_record
from viewer import write_wiki

# --------------------------------------------------------------------------- helpers


def load_json(path, default):
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def discover_images(root, recurse=True):
    root = Path(root)
    walker = root.rglob("*") if recurse else root.glob("*")
    out = []
    for p in sorted(walker):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return out


def custom_id_for(rel_path):
    return "img_" + hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:24]


def probe_downscaled_size(path):
    try:
        with Image.open(path) as im:
            w, h = im.size
        scale = min(1.0, MAX_DIM / max(w, h)) if max(w, h) else 1.0
        return max(1, int(w * scale)), max(1, int(h * scale))
    except Exception:
        return None


def encode_image(path):
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, MAX_DIM / max(w, h)) if max(w, h) else 1.0
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=JPEG_QUALITY)
            data = buf.getvalue()
        return base64.standard_b64encode(data).decode("ascii")
    except Exception:
        return None


def image_tokens(w, h):
    return min(1600, round((w * h) / 750))


def build_request(rel_path, b64, model_id):
    return {
        "custom_id": custom_id_for(rel_path),
        "params": {
            "model": model_id,
            "max_tokens": 700,
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "tools": [RECORD_TOOL],
            "tool_choice": {"type": "tool", "name": "record_artwork"},
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": f"Path: {rel_path}\nCatalogue this image."},
            ]}],
        },
    }


def extract_record(message):
    for block in message.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    return None


def chunk(prepared):
    cur, cur_bytes = [], 0
    for req, nbytes in prepared:
        if cur and (len(cur) >= CHUNK_SIZE or cur_bytes + nbytes > MAX_BATCH_BYTES):
            yield cur
            cur, cur_bytes = [], 0
        cur.append(req)
        cur_bytes += nbytes
    if cur:
        yield cur

# --------------------------------------------------------------------------- estimate


def do_estimate(root, images, catalog):
    todo = [p for p in images if str(p.relative_to(root)) not in catalog]
    tin = tout = unreadable = 0
    for p in todo:
        dims = probe_downscaled_size(p)
        if dims is None:
            unreadable += 1
            continue
        tin += image_tokens(*dims) + OVERHEAD_IN
        tout += EST_OUT

    print("\n" + "=" * 56)
    print(f"  Images found            : {len(images):,}")
    print(f"  Already done            : {len(images) - len(todo):,}")
    print(f"  To process              : {len(todo):,}")
    if unreadable:
        print(f"  Unreadable (skipped)    : {unreadable:,}")
    print(f"  Est. input tokens       : ~{tin:,}")
    print(f"  Est. output tokens      : ~{tout:,}")
    print("-" * 56)
    print("  Estimated one-time cost (Batch API, current prices):")
    for m in MODELS.values():
        cost = tin / 1_000_000 * m["in"] + tout / 1_000_000 * m["out"]
        print(f"    {m['label']:<44} ~${cost:,.2f}")
    print("=" * 56)
    print("  These are over-estimates; the real bill is usually lower.")
    print("  Nothing was charged. No API key was used.\n")

# --------------------------------------------------------------------------- real run


def wait_for_batch(client, batch_id):
    while True:
        b = client.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            return
        c = b.request_counts
        done = c.succeeded + c.errored + c.canceled + c.expired
        print(f"    ...working (done {done}, in flight {c.processing})", flush=True)
        time.sleep(POLL_SECONDS)


def merge_batch(client, batch_id, id_to_path, catalog):
    ok = failed = 0
    for entry in client.messages.batches.results(batch_id):
        rel = id_to_path.get(entry.custom_id)
        if rel is None:
            continue
        if entry.result.type == "succeeded":
            rec = extract_record(entry.result.message)
            if rec is None:
                failed += 1
                continue
            rec["path"] = rel
            catalog[rel] = clean_record(rec)
            ok += 1
        else:
            failed += 1
    return ok, failed


def write_csvs(out_dir, catalog):
    rows = list(catalog.values())
    with open(Path(out_dir) / CATALOG_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = dict(r)
            if isinstance(r.get("tags"), list):
                r["tags"] = "; ".join(r["tags"])
            w.writerow(r)
    review_cols = ["path", "artist", "artist_confidence", "attribution_source", "title", "date_or_period", "movement", "notes"]
    flagged = [r for r in rows if r.get("needs_review")
               or r.get("artist_confidence") in {"low", "medium", "unknown"}
               or r.get("attribution_source") == "unknown"]
    with open(Path(out_dir) / REVIEW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=review_cols, extrasaction="ignore")
        w.writeheader()
        for r in flagged:
            w.writerow(r)
    return len(rows), len(flagged)


def do_run(root, out_dir, images, catalog, model_id, limit=None):
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nNo API key found. Set ANTHROPIC_API_KEY first (I can walk you through it).")
        return
    client = anthropic.Anthropic()

    state = load_json(Path(out_dir) / STATE_FILE, {"pending_batch_id": None, "id_to_path": {}})
    if state.get("pending_batch_id"):
        bid = state["pending_batch_id"]
        print(f"Resuming an unfinished batch ({bid})...")
        try:
            wait_for_batch(client, bid)
            ok, failed = merge_batch(client, bid, state["id_to_path"], catalog)
            print(f"  recovered {ok} ({failed} to retry)")
            save_json(Path(out_dir) / CATALOG_FILE, catalog)
        except Exception as e:
            print(f"  could not recover it ({e}); those items will be redone.")
        save_json(Path(out_dir) / STATE_FILE, {"pending_batch_id": None, "id_to_path": {}})

    todo = [p for p in images if str(p.relative_to(root)) not in catalog]
    if limit:
        todo = todo[:limit]
    print(f"\nPreparing {len(todo):,} image(s)... (this reads and shrinks each one)")

    prepared, id_to_path_all, skipped = [], {}, 0
    for i, p in enumerate(todo, 1):
        rel = str(p.relative_to(root))
        b64 = encode_image(p)
        if b64 is None:
            skipped += 1
            continue
        req = build_request(rel, b64, model_id)
        prepared.append((req, len(b64)))
        id_to_path_all[req["custom_id"]] = rel
        if i % 200 == 0:
            print(f"  prepared {i:,}/{len(todo):,}")
    if skipped:
        print(f"  {skipped} unreadable image(s) skipped.")
    if not prepared:
        print("Everything here is already catalogued; refreshing the viewer.")
        write_csvs(out_dir, catalog)
        wiki = write_wiki(out_dir, catalog)
        print(f"Open {wiki.name} in your browser.")
        return

    total_ok = total_failed = 0
    for i, batch_reqs in enumerate(chunk(prepared), 1):
        cids = {r["custom_id"] for r in batch_reqs}
        id_to_path = {k: v for k, v in id_to_path_all.items() if k in cids}
        print(f"\nBatch {i}: sending {len(batch_reqs):,} image(s)...")
        batch = client.messages.batches.create(requests=batch_reqs)
        save_json(Path(out_dir) / STATE_FILE, {"pending_batch_id": batch.id, "id_to_path": id_to_path})
        wait_for_batch(client, batch.id)
        ok, failed = merge_batch(client, batch.id, id_to_path, catalog)
        total_ok += ok
        total_failed += failed
        print(f"  {ok} done, {failed} failed/skipped")
        save_json(Path(out_dir) / CATALOG_FILE, catalog)
        save_json(Path(out_dir) / STATE_FILE, {"pending_batch_id": None, "id_to_path": {}})

    n_total, n_flagged = write_csvs(out_dir, catalog)
    wiki = write_wiki(out_dir, catalog)
    print(f"\nDone. {total_ok} new this run, {total_failed} to retry.")
    print(f"Catalogue holds {n_total} records; {n_flagged} flagged for review.")
    print(f"Files written to: {out_dir}")
    print(f"Open {wiki.name} in your browser to look through them.")
    if total_failed:
        print("Re-run and choose the same option to retry the failures.")

# --------------------------------------------------------------------------- menu


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def main():
    print("\n  Reference-library cataloguer")
    print("  " + "-" * 30)
    root_in = ask(f"  Folder to catalogue\n    [Enter = {DEFAULT_ROOT}]\n  > ").strip().strip('"')
    root = Path(root_in or DEFAULT_ROOT).expanduser()
    if not root.is_dir():
        print(f"\n  Can't find that folder: {root}")
        print("  Check the path and run it again.")
        return
    root = root.resolve()
    out_dir = root
    catalog = load_json(out_dir / CATALOG_FILE, {})
    for rec in catalog.values():
        clean_record(rec)

    sub = ask("  Include images inside subfolders too? [Y/n]\n  > ").strip().lower()
    recurse = not sub.startswith("n")

    print("\n  Scanning for images...")
    images = discover_images(root, recurse)
    scope = "including subfolders" if recurse else "top level only"
    print(f"  Found {len(images):,} image file(s) ({scope}).")

    print("\n  What would you like to do?")
    print("    1) Estimate the cost   (free, no API key, no charge)")
    print("    2) Test run on 25 images  (small charge, to check quality)")
    print("    3) Full run on everything (the real thing)")
    print("    4) Build the HTML viewer from existing results (free)")
    choice = ask("  > ").strip()

    if choice == "1":
        do_estimate(root, images, catalog)
        return

    if choice == "4":
        if not catalog:
            print("\n  No results yet. Do a run first (option 2 or 3), then come back.")
            return
        save_json(out_dir / CATALOG_FILE, catalog)
        write_csvs(out_dir, catalog)
        wiki = write_wiki(out_dir, catalog)
        print(f"\n  Built {wiki.name} with {len(catalog):,} record(s).")
        print("  Double-click it in the folder to open it in your browser.")
        return

    if choice in ("2", "3"):
        print("\n  Which model?")
        for k, m in MODELS.items():
            print(f"    {k}) {m['label']}")
        mk = ask("  > ").strip()
        model = MODELS.get(mk)
        if not model:
            print("  Not a valid choice. Run it again.")
            return
        limit = 25 if choice == "2" else None
        do_run(root, out_dir, images, catalog, model["id"], limit=limit)
        return

    print("  Not a valid choice. Run it again.")


if __name__ == "__main__":
    main()
