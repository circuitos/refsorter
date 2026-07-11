# refsorter

Contextualises a folder of painter reference images. Point it at your library
and it identifies each work with Claude's vision (via the Message Batches API,
which costs half the normal rate), then builds a searchable offline wiki of
the whole collection. Nothing is ever moved, renamed, or written over: your
images are read, never touched.

## What it produces

All four files are written into the library root, next to your images:

| File | What it is |
| --- | --- |
| `catalog.json` | The master file. Everything else is generated from it. |
| `catalog.csv` | The same data as a spreadsheet, for Excel or Sheets. |
| `review_queue.csv` | Only the items where the artist attribution is an uncertain guess. |
| `wiki.html` | A self-contained viewer. Double-click it, no internet needed. |

`catalog.json` is the single source of truth. The CSVs and `wiki.html` are
derived from it and can be rebuilt at any time for free (menu option 4).

Each record holds: artist, confidence, title, date, movement, medium, subject,
palette, composition notes, art-historical context, and search tags. Artist
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

The sensible order is 1, then 2, then 3.

Expect roughly $0.006 per image on Sonnet batch pricing, so a 5,000 image
library is in the $15 to $30 range. Option 1 gives you the real number for
your folder before you spend anything. Model IDs and prices drift; both live
at the top of `catalog_refs.py` as plain editable settings, with a note of
when they were last checked.

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
| `viewer.py` + `templates/wiki.html` | The offline wiki builder and its page template. |
| `make_standalone.py` | Inlines everything into `dist/catalog_refs.py`. |

## Rules the code lives by

These are deliberate. Changes should not break them.

- Images are never moved, renamed, or overwritten. Outputs go into the
  library root only.
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
- `MOVEMENT_CANON` and `MOVEMENT_INFO` stay in sync: every canon value has an
  info entry with years, blurb, and wiki slug ("Other" has null years/wiki).
- Batches are chunked at 1,000 requests / 200 MB, the in-flight batch id is
  persisted to `.catalog_state.json` for resume, and failed items are simply
  absent from the catalogue so a re-run retries them.
- `max_tokens: 700` and the 60-word caps in the prompt are cost controls.
- Paths with `! `, spaces, and backslashes are normal here. Test with them.
- User data (catalogues, state, images) is never committed to this repo.
