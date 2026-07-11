# refsorter

Contextualises a folder of painter reference images. Point it at your library
and it identifies each work with Claude's vision (via the Message Batches API,
which costs half the normal rate), then builds a searchable offline wiki of
the whole collection. Cataloguing never moves, renames, or writes over an
image: your files are read, never touched. The one thing that ever moves a
file is the sorter (menu option 5), which only acts on a plan it has shown
you first, and every sort can be undone in one step.

## What it produces

Only `wiki.html` sits at the library root, next to your images — it has to,
because it references them by relative path. Every other working file lives
in a `_database` folder at the root, keeping the library itself tidy.
Libraries created before this layout are tidied automatically on the next
run.

| File | Where | What it is |
| --- | --- | --- |
| `wiki.html` | library root | A self-contained viewer. Double-click it, no internet needed. |
| `catalog.json` | `_database` | The master file. Everything else is generated from it. |
| `catalog.csv` | `_database` | The same data as a spreadsheet, for Excel or Sheets. |
| `review_queue.csv` | `_database` | Only the items where the artist attribution is an uncertain guess. |
| `artists.json` | `_database` | The artist index: one entry per painter. Hand-editable. |

`catalog.json` is the single source of truth. The CSVs and `wiki.html` are
derived from it and can be rebuilt at any time for free (menu option 4).

Each record holds: artist, confidence, title, date, movement, medium, subject,
palette, composition notes, work-specific context, and search tags. Facts
about the *painter* (years, nationality, school, one bio) live once per
artist in `artists.json`, not repeated per image — see "The artist index". Artist
names found in your folder and file names are taken as ground truth; the model
only guesses when the path tells it nothing, and it reports honest confidence
when it does. Uncertain guesses are flagged for review.

## Setup

You need Python 3 with two packages, and an Anthropic API key
(from https://console.anthropic.com/).

```
pip install -r requirements.txt
```

Set the key in PowerShell (once, then restart the terminal):

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
```

## Running it

```
python catalog_refs.py
```

It asks for the folder to catalogue, whether to include subfolders, and what to
do. One catalogue can span a whole library: if the folder you point at sits
inside a folder that already has a `catalog.json`, the tool grows that existing
library instead of starting a separate one, so you can catalogue a subfolder at
a time and everything lands in one master viewer at the root. You can also move
an existing library to another folder (image links are fixed automatically) or
start a fresh one. The menu options:

1. **Estimate the cost.** Free, no API key used, nothing sent anywhere.
2. **Test run on 25 images.** A small charge, to check the quality first.
3. **Full run.** The real thing. Progress is saved as it goes; if it is
   interrupted, run it again and it picks up where it left off. Anything
   that failed is simply retried on the next run.
4. **Rebuild the viewer** from existing results. Free.
5. **Sort catalogued images into painter folders.** Shows its full plan
   first; nothing moves until you say so. See below.
6. **Undo the last sort.** Replays the journal in reverse.

The sensible order is 1, then 2, then 3.

Expect roughly $0.006 per image on Sonnet batch pricing, so a 5,000 image
library is in the $15 to $30 range. Option 1 gives you the real number for
your folder before you spend anything. Model IDs and prices drift; both live
at the top of `catalog_refs.py` as plain editable settings, with a note of
when they were last checked.

## The artist index

`_database/artists.json` holds one entry per painter: canonical
name, birth/death years, nationality, primary school, a single 60-word bio,
and a Wikipedia title, plus an alias map that folds spelling variants
("Theodoros Ralli" / "Theodoros Rallis") onto one painter. It exists so
artist-level facts are generated **once**, not re-told slightly differently
on every card by that painter.

- It fills itself in automatically after each catalogue run: any painters new
  to the catalogue get looked up in one small text-only API call (no images,
  well under a cent for a whole library).
- The wiki shows the entry as an "About the painter" panel on every work by
  that painter, and search reaches it too — searching "Swedish" finds all
  works by Swedish painters even when no record mentions it.
- It is plain JSON and hand-editable. Your edits win: lookups only fill
  fields that are still empty, never overwrite a value.
- To backfill bios for works catalogued before the index existed, run
  option 3 on an already-done folder: nothing is re-sent, but the index is
  topped up and the wiki rebuilt.

Because the biography lives here, the per-image `context` field is
work-specific by instruction — which also trims the output tokens each
image pays for.

## Sorting into painter folders

Cataloguing does the expensive looking; sorting is a cheap, deterministic file
operation on top of it. Point the tool at a messy folder, catalogue it (option
2 or 3), then choose option 5. It works in three stages:

1. **Roster.** Painter identities come from the artist index above; any
   names it does not know yet are looked up first. If a year is wrong, edit
   `artists.json` and it stays fixed.
2. **Plan.** Every proposed move is written to `_database/sort_plan.csv` and summarised.
   Nothing has moved yet. Open the CSV and delete any rows you disagree with,
   then re-run option 5 and choose `a` to apply the edited plan.
3. **Apply.** Files move, every operation is journaled to `sort_undo.json`,
   the catalogue's paths are rewritten, and the CSVs and wiki are rebuilt so
   no links break. Option 6 replays the journal in reverse.

The rules it sorts by:

- Folders are named in the library's existing convention:
  `John Singer Sargent 1856-1925`, or `Dean Mitchell 1957-present` for living
  painters, or the bare name when the years are not securely known.
- New painter folders are created **inside the folder each image already
  lives in** (its top-level subfolder of the scanned root), so grouping
  folders like `! RUSSIANS` keep their meaning instead of dissolving.
- Only records whose attribution is secure (`given` or `high` confidence)
  move. Everything uncertain stays exactly where it is — those are the
  `review_queue.csv` items.
- A file already sitting in its painter's folder is left alone; a file
  sitting in a *different* painter's folder is pulled out to the scanned
  root's folder for its real painter.
- Optionally, existing painter folders that lack years get them added
  (`Anders Zorn` → `Anders Zorn 1860-1920`); folders whose years disagree
  with the roster are only flagged, never auto-renamed. Folder renames are
  journaled and undoable like everything else.
- If two files would land in the folder with the same name, the newcomer gets
  a ` (2)` suffix rather than overwriting. Emptied folders are left in place.

## Single-file version

The repo is split into modules for development, but the Desktop workflow is
one file you can copy anywhere:

```
python make_standalone.py
```

This writes `dist/catalog_refs.py`, a self-contained script that behaves
identically to running from the repo.

## Layout

| File | Contents |
| --- | --- |
| `catalog_refs.py` | Entry point: settings, interactive menu, batch logic. |
| `record_schema.py` | The system prompt, the tool schema, and the movement canon. |
| `cleaning.py` | The repair pipeline every record passes through. |
| `artists.py` | The artist index: canonical names, years, bios, aliases. |
| `sorter.py` | The painter-folder sorter: plan, apply, undo. |
| `viewer.py` + `templates/wiki.html` | The offline wiki builder and its page template. |
| `make_standalone.py` | Inlines everything into `dist/catalog_refs.py`. |

## Rules the code lives by

These are deliberate. Changes should not break them.

- Cataloguing never moves, renames, or overwrites an image. All working
  files go into `_database` at the library root; `wiki.html` alone sits at
  the root itself, because its image links are relative and break anywhere
  else. Legacy root-level layouts are migrated automatically
  (`migrate_layout`). The sorter (`sorter.py`) is the single, explicit
  exception: it moves files only from a plan the user has seen, journals
  every operation to `sort_undo.json`, keeps the catalogue's paths in sync,
  and can undo the whole sort in one step. Nothing else may move a file.
- Image paths are stored relative to the library root, and a run on a subfolder
  grows the nearest existing library at or above it (`find_library_root`), so
  the whole tree shares one master catalogue and one viewer. Moving a library
  (`reposition_library`) rewrites those relative paths so links keep resolving.
- `wiki.html` stays one self-contained file that works over `file://` with
  zero network dependencies. It references images by relative path, which is
  why it must live in the library root.
- Every record passes through the cleaning pipeline, both fresh from the API
  and when an existing catalogue is loaded. This auto-repairs old data. The
  order is fixed: strip leaked tool syntax, coerce tags to a list, normalise
  the movement onto the canonical list, recompute the review flag.
- `needs_review` flags artist uncertainty only. A securely named artist with
  an unknown title or date is not review-worthy.
- Artist-level facts live once in `artists.json`, keyed by canonical name
  with an alias map for variants. Lookups only fill empty fields — a value
  the user edited by hand is never overwritten. Per-image `context` stays
  about the work, never the painter's biography.
- `MOVEMENT_CANON` and `MOVEMENT_INFO` stay in sync: every canon value has an
  info entry with years, blurb, and wiki slug ("Other" has null years/wiki).
- Batches are chunked at 1,000 requests / 200 MB, the in-flight batch id is
  persisted to `.catalog_state.json` for resume, and failed items are simply
  absent from the catalogue so a re-run retries them.
- `max_tokens: 700` and the 60-word caps in the prompt are cost controls.
- Paths with `! `, spaces, and backslashes are normal here. Test with them.
- User data (catalogues, state, images) is never committed to this repo.
