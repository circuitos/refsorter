"""Sort catalogued images into per-painter folders.

Cataloguing (menu options 2/3) does the expensive vision work; sorting is a
deterministic file operation on top of the catalogue, in three stages:

  artist index  ->  plan (_database/sort_plan.csv, nothing moves)  ->  apply (journaled)

- Painter identities come from the artist database (artists.py / artists.json):
  name variants merge onto one canonical painter with birth/death years.
- New folders follow the library's existing convention "Name 1856-1925"
  ("Name 1957-present" for living painters) and are created inside the folder
  being sorted, so grouping folders like "! RUSSIANS" keep their meaning.
- Only records with a secure attribution (given/high confidence) move;
  everything else stays exactly where it is.
- Applying writes _database/sort_undo.json; menu option 6 replays it in reverse.

This module is the single, explicit exception to the rule that images are
never moved: only here, only after showing the plan, always undoable.
"""

import csv
import os
from pathlib import Path

from artists import ARTISTS_FILE, DB_DIR, _load_json, _save_json, db_dir, ensure_artists, folder_hints, norm, roster_years, split_folder_years  # noqa: E501 - one line so the standalone build can strip it

PLAN_FILE = "sort_plan.csv"
UNDO_FILE = "sort_undo.json"
SORTABLE_CONFIDENCE = {"given", "high"}
PLAN_COLUMNS = ["action", "src", "dest", "artist", "confidence", "note"]


def _ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def folder_name_for(canonical, entry):
    years = roster_years(entry)
    return "%s %s" % (canonical, years) if years else canonical


# ------------------------------------------------------------------ plan


def _folder_artist(folder_name, roster):
    """The canonical artist a folder name refers to, or None."""
    base, _years = split_folder_years(folder_name)
    return roster["aliases"].get(norm(base))


def scope_records(lib_root, scan_root, catalog, recurse):
    """Catalogue records under scan_root as (path_rel_to_lib, path_rel_to_scan, record)."""
    lib_root, scan_root = Path(lib_root), Path(scan_root)
    same = scan_root == lib_root
    scan_rel = None if same else scan_root.relative_to(lib_root)
    out = []
    for rel, rec in catalog.items():
        p = Path(rel)
        if same:
            rts = p
        else:
            try:
                rts = p.relative_to(scan_rel)
            except ValueError:
                continue
        if not recurse and len(rts.parts) != 1:
            continue
        out.append((p, rts, rec))
    return out


def build_plan(lib_root, scan_root, catalog, recurse, roster, add_years, to_root=False):
    """Compute the full plan. Returns (rows, stats); nothing is touched.

    to_root empties a staging folder outward: every sortable file goes to a
    painter folder at the library root (joining existing ones there), instead
    of into painter folders inside the scanned folder."""
    lib_root, scan_root = Path(lib_root), Path(scan_root)
    scan_rel = Path(".") if scan_root == lib_root else scan_root.relative_to(lib_root)
    rows = []
    stats = {"moves": 0, "renames": 0, "flags": 0, "already": 0, "left": 0}
    new_folders, dir_cache = set(), {}

    def existing_artist_folder(parent_rel, canonical):
        key = str(parent_rel)
        if key not in dir_cache:
            d = lib_root / parent_rel
            dir_cache[key] = [e.name for e in os.scandir(d) if e.is_dir()] if d.is_dir() else []
        for name in dir_cache[key]:
            if _folder_artist(name, roster) == canonical:
                return name
        return None

    for p, rts, rec in scope_records(lib_root, scan_root, catalog, recurse):
        artist_raw = (rec.get("artist") or "").strip()
        if not artist_raw or rec.get("artist_confidence") not in SORTABLE_CONFIDENCE:
            stats["left"] += 1
            continue
        canonical = roster["aliases"].get(norm(artist_raw))
        if not canonical:
            stats["left"] += 1
            continue
        if to_root:
            # Already sorted only if it sits in its painter's ROOT folder;
            # a painter folder inside the staging area still empties out.
            already = len(p.parts) > 1 and _folder_artist(p.parts[0], roster) == canonical
        else:
            already = any(_folder_artist(part, roster) == canonical for part in p.parts[:-1])
        if already:
            stats["already"] += 1
            continue
        if to_root:
            dest_parent = Path(".")
        else:
            # Keep grouping folders: the painter folder goes inside the file's
            # top-level subfolder of the scanned root, unless that subfolder is
            # another painter's (a misfile), which sorts to the scanned root.
            top = rts.parts[0] if len(rts.parts) > 1 else None
            if top is None or _folder_artist(top, roster):
                dest_parent = scan_rel
            else:
                dest_parent = scan_rel / top
        entry = roster["artists"].get(canonical, {})
        folder = existing_artist_folder(dest_parent, canonical) or folder_name_for(canonical, entry)
        dest = dest_parent / folder / p.name
        if dest == p:
            stats["already"] += 1
            continue
        if not (lib_root / dest_parent / folder).is_dir():
            new_folders.add(str(dest_parent / folder))
        rows.append({"action": "move", "src": str(p), "dest": str(dest),
                     "artist": canonical, "confidence": rec.get("artist_confidence", ""),
                     "note": ""})
        stats["moves"] += 1

    if add_years:
        for d in sorted(x for x in scan_root.rglob("*") if x.is_dir()):
            name = d.name
            canonical = _folder_artist(name, roster)
            if not canonical:
                continue
            entry = roster["artists"].get(canonical, {})
            expected = roster_years(entry)
            base, have = split_folder_years(name)
            rel = str(d.relative_to(lib_root))
            if have is None:
                if expected:
                    target = "%s %s" % (base, expected)  # keep the folder's own spelling
                    if (d.parent / target).exists():
                        rows.append({"action": "flag", "src": rel, "dest": "", "artist": canonical,
                                     "confidence": "", "note": "wanted to rename to '%s' but it already exists" % target})
                        stats["flags"] += 1
                    else:
                        rows.append({"action": "rename_folder", "src": rel,
                                     "dest": str(d.relative_to(lib_root).parent / target),
                                     "artist": canonical, "confidence": "", "note": "add years"})
                        stats["renames"] += 1
            elif expected and have != expected:
                rows.append({"action": "flag", "src": rel, "dest": "", "artist": canonical,
                             "confidence": "", "note": "folder says %s but the artist index says %s "
                             "(fix whichever is wrong: the folder by hand, or %s)" % (have, expected, ARTISTS_FILE)})
                stats["flags"] += 1

    stats["new_folders"] = len(new_folders)
    return rows, stats


def write_plan(lib_root, rows):
    path = db_dir(lib_root) / PLAN_FILE
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PLAN_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


# ------------------------------------------------------------------ apply / undo


def _apply_to_catalog(catalog, ops):
    """Re-key the catalogue after file moves and folder renames so every
    record's key and path match where the image now lives."""
    for op in ops:
        if op["op"] == "move":
            rec = catalog.pop(op["src"], None)
            if rec is not None:
                rec["path"] = op["dst"]
                catalog[op["dst"]] = rec
        else:  # folder rename: rewrite the prefix of everything inside it
            pre = op["src"] + os.sep
            for key in [k for k in catalog if k.startswith(pre)]:
                nk = op["dst"] + key[len(op["src"]):]
                rec = catalog.pop(key)
                rec["path"] = nk
                catalog[nk] = rec


def apply_plan(lib_root, catalog, rebuild):
    """Execute sort_plan.csv (honouring any edits), journal every operation to
    sort_undo.json, then re-key the catalogue and rebuild the outputs."""
    lib_root = Path(lib_root)
    plan_path = Path(lib_root) / DB_DIR / PLAN_FILE
    if not plan_path.exists():
        print("\n  No %s here. Build a plan first (option 5)." % os.path.join(DB_DIR, PLAN_FILE))
        return
    with open(plan_path, "r", encoding="utf-8-sig", newline="") as f:
        plan = list(csv.DictReader(f))
    moves = [r for r in plan if (r.get("action") or "").strip() == "move"]
    renames = [r for r in plan if (r.get("action") or "").strip() == "rename_folder"]
    if not moves and not renames:
        print("\n  The plan has no move or rename rows; nothing to do.")
        return

    ops, missing, collided = [], 0, 0
    for r in moves:  # files first; folder renames go last and carry contents along
        src = lib_root / r["src"]
        if not src.is_file():
            missing += 1
            continue
        dest = lib_root / r["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        final, n = dest, 2
        while final.exists():
            final = dest.with_name("%s (%d)%s" % (dest.stem, n, dest.suffix))
            n += 1
        if final != dest:
            collided += 1
        src.rename(final)
        ops.append({"op": "move", "src": r["src"], "dst": str(final.relative_to(lib_root))})
    skipped_renames = 0
    for r in renames:
        src, dest = lib_root / r["src"], lib_root / r["dest"]
        if not src.is_dir() or dest.exists():
            skipped_renames += 1
            continue
        src.rename(dest)
        ops.append({"op": "rename", "src": r["src"], "dst": r["dest"]})

    if not ops:
        print("\n  Nothing could be applied (sources missing?). Rebuild the plan.")
        return
    _save_json(db_dir(lib_root) / UNDO_FILE, {"ops": ops})
    _apply_to_catalog(catalog, ops)
    try:
        plan_path.unlink()
    except OSError:
        pass
    rebuild(catalog)

    n_moves = sum(1 for o in ops if o["op"] == "move")
    n_ren = len(ops) - n_moves
    print("\n  Moved %d file(s), renamed %d folder(s)." % (n_moves, n_ren))
    if collided:
        print("  %d file(s) got a ' (2)' style suffix to avoid overwriting a namesake." % collided)
    if missing:
        print("  %d planned file(s) were no longer where the plan expected; skipped." % missing)
    if skipped_renames:
        print("  %d folder rename(s) skipped (source gone or target exists)." % skipped_renames)
    print("  Emptied folders are left in place; delete them by hand if you like.")
    print("  Catalogue, CSVs and wiki updated. Undo everything with option 6.")


def undo_sort(lib_root, catalog, rebuild):
    """Reverse the last apply, using the sort_undo.json journal."""
    lib_root = Path(lib_root)
    journal = _load_json(Path(lib_root) / DB_DIR / UNDO_FILE, None)
    if not journal or not journal.get("ops"):
        print("\n  No sort to undo (no %s at the library root)." % os.path.join(DB_DIR, UNDO_FILE))
        return
    undone, problems = [], 0
    for op in reversed(journal["ops"]):
        src, dst = lib_root / op["dst"], lib_root / op["src"]
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            undone.append({"op": op["op"], "src": op["dst"], "dst": op["src"]})
        else:
            problems += 1
    _apply_to_catalog(catalog, undone)
    if not problems:
        try:
            (lib_root / DB_DIR / UNDO_FILE).unlink()
        except OSError:
            pass
    rebuild(catalog)
    print("\n  Undid %d operation(s)." % len(undone))
    if problems:
        print("  %d operation(s) could not be reversed (file moved or name taken since);" % problems)
        print("  the journal is kept so you can sort those out by hand.")


# ------------------------------------------------------------------ interactive flow


def run_sort(lib_root, scan_root, catalog, recurse, rebuild):
    """Menu option 5: artist index -> plan -> confirm -> apply."""
    lib_root, scan_root = Path(lib_root), Path(scan_root)

    if (lib_root / DB_DIR / PLAN_FILE).exists():
        print("\n  A plan from a previous run exists: %s" % os.path.join(DB_DIR, PLAN_FILE))
        print("    [Enter] Rebuild it fresh")
        print("    a)      Apply it as it stands (honours your edits)")
        if _ask("  > ").strip().lower() == "a":
            apply_plan(lib_root, catalog, rebuild)
            return

    scoped = scope_records(lib_root, scan_root, catalog, recurse)
    if not scoped:
        print("\n  The catalogue has nothing under this folder yet.")
        print("  Catalogue it first (option 2 or 3), then sort.")
        return
    raws = sorted({(r.get("artist") or "").strip() for _, _, r in scoped
                   if (r.get("artist") or "").strip()
                   and r.get("artist_confidence") in SORTABLE_CONFIDENCE})
    if not raws:
        print("\n  No securely attributed records under this folder; nothing safe to sort.")
        print("  (Uncertain attributions are listed in %s.)" % os.path.join(DB_DIR, "review_queue.csv"))
        return

    roster = ensure_artists(lib_root, raws, folder_hints(lib_root))
    if roster is None:
        return

    to_root = False
    if scan_root != lib_root:
        print("\n  Where should these images end up?")
        print("    [Enter] In painter folders inside the scanned folder")
        print("            (keeps groupings like '! RUSSIANS' intact)")
        print("    r)      In painter folders at the library root, joining the")
        print("            existing ones there (empties a staging folder outward)")
        to_root = _ask("  > ").strip().lower() == "r"

    ans = _ask("\n  Also add missing birth/death years to existing painter folders\n"
               "  here (e.g. 'Anders Zorn' -> 'Anders Zorn 1860-1920')? [Y/n]\n  > ")
    add_years = not ans.strip().lower().startswith("n")

    rows, stats = build_plan(lib_root, scan_root, catalog, recurse, roster, add_years, to_root)
    flags = [r for r in rows if r["action"] == "flag"]
    if not any(r["action"] in ("move", "rename_folder") for r in rows):
        print("\n  Everything securely attributed is already in its painter's folder.")
        for r in flags:
            print("  Check: %s - %s" % (r["src"], r["note"]))
        return

    write_plan(lib_root, rows)
    print("\n" + "=" * 56)
    print("  Plan written to %s - nothing has moved yet." % os.path.join(DB_DIR, PLAN_FILE))
    print("    Files to move            : %d (into %d new folder(s))" % (stats["moves"], stats["new_folders"]))
    print("    Folders to add years to  : %d" % stats["renames"])
    print("    Already sorted           : %d" % stats["already"])
    print("    Left alone (uncertain)   : %d" % stats["left"])
    if flags:
        print("    Needs a human look       : %d" % len(flags))
        for r in flags:
            print("      %s\n        %s" % (r["src"], r["note"]))
    print("=" * 56)
    print("    [Enter] Apply the plan now (undoable with option 6)")
    print("    e)      Keep the plan for editing; re-run option 5 and pick 'a'")
    print("    q)      Discard the plan")
    pick = _ask("  > ").strip().lower()
    if pick == "q":
        try:
            (lib_root / DB_DIR / PLAN_FILE).unlink()
        except OSError:
            pass
        print("  Plan discarded; nothing moved.")
        return
    if pick == "e":
        print("  Kept. Open %s, delete any rows you disagree with," % os.path.join(DB_DIR, PLAN_FILE))
        print("  then run option 5 again and choose 'a' to apply.")
        return
    apply_plan(lib_root, catalog, rebuild)
