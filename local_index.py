#!/usr/bin/env python3
"""local_index.py - free, offline visual index for an image folder.

Embeds every image with a CLIP-family model on your own GPU (no API, no
tokens), stores the vectors in `_database/clip_index`, then lets you:

  index   embed the images (chunked; stop any time and re-run to resume)
  search  find images by text ("spiral"), by example (--like), or by tag
  tag     zero-shot keyword tags from design_vocab.json, plus tags.csv

Originals are only ever read. Everything is written under
<library>/_database/clip_index (and search pages under <library>/_database).

  python local_index.py index  "D:\\Dropbox\\! REF\\Design"
  python local_index.py search "D:\\Dropbox\\! REF\\Design" "spiral" -n 80
  python local_index.py tag    "D:\\Dropbox\\! REF\\Design"
"""

import argparse
import csv
import html
import json
import os
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import numpy as np
from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
DEFAULT_MODEL = "ViT-L-14"
DEFAULT_PRETRAINED = "laion2b_s32b_b82k"
DB_DIR = "_database"
INDEX_SUB = "clip_index"
TEXT_TEMPLATES = ["{}", "a graphic design featuring {}", "an image of {}"]
VOCAB_FILE = Path(__file__).with_name("design_vocab.json")


# --------------------------------------------------------------------- files

def index_dir(root):
    d = Path(root) / DB_DIR / INDEX_SUB
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def discover(root, recurse=True):
    """Relative (forward-slash) paths of every image under root."""
    root = str(root)
    out = []
    if recurse:
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d != DB_DIR]
            for f in fn:
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                    out.append(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    else:
        for f in os.listdir(root):
            if os.path.isfile(os.path.join(root, f)) and os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                out.append(f)
    return sorted(out)


def load_image(path):
    """Open any supported image as RGB. Transparent images go onto white."""
    with Image.open(path) as im:
        try:
            im.draft("RGB", (640, 640))  # fast JPEG downscale on decode
        except Exception:
            pass
        im.seek(0)
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            bg.alpha_composite(rgba)
            return bg.convert("RGB")
        return im.convert("RGB")


# --------------------------------------------------------------------- model

class Embedder:
    def __init__(self, name, pretrained):
        import torch
        import open_clip
        self.torch = torch
        self.name, self.pretrained = name, pretrained
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading {name} ({pretrained}) on {self.dev} ...", flush=True)
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            name, pretrained=pretrained, device=self.dev)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(name)
        self.scale = float(self.model.logit_scale.exp().item())

    def _ctx(self):
        t = self.torch
        return t.autocast(self.dev, dtype=t.float16, enabled=self.dev == "cuda")

    def images(self, tensors):
        t = self.torch
        with t.inference_mode(), self._ctx():
            x = t.stack(tensors).to(self.dev)
            f = self.model.encode_image(x)
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()

    def texts(self, strings):
        t = self.torch
        with t.inference_mode(), self._ctx():
            tok = self.tokenizer(strings).to(self.dev)
            f = self.model.encode_text(tok)
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()

    def query(self, text):
        """Prompt-ensemble embedding for a short concept like 'spiral'."""
        v = self.texts([t.format(text) for t in TEXT_TEMPLATES]).mean(axis=0)
        return v / np.linalg.norm(v)


# --------------------------------------------------------------------- index

def shard_files(d):
    return sorted(Path(d).glob("shard_*.npz"))


def load_index(root):
    """-> (paths, embeddings[N, D] float32, unit length). Later shards win."""
    d = index_dir(root)
    seen = {}
    for s in shard_files(d):
        try:
            with np.load(s) as z:
                for p, e in zip(z["paths"].tolist(), z["emb"]):
                    seen[p] = e
        except Exception as e:
            print(f"warning: skipping unreadable shard {s.name}: {e}", file=sys.stderr)
    if not seen:
        sys.exit("No index yet. Run:  local_index.py index <library>")
    paths = list(seen)
    emb = np.stack([seen[p] for p in paths]).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    return paths, emb


def cmd_index(a):
    root = Path(a.root)
    d = index_dir(root)
    meta_path = d / "meta.json"
    meta = load_json(meta_path, None)
    want = {"model": a.model, "pretrained": a.pretrained}
    if meta and meta != want:
        sys.exit(f"Index was built with {meta}; refusing to mix in {want}. Use a new library _database or delete {d}.")
    save_json(meta_path, want)

    done = set()
    for s in shard_files(d):
        try:
            with np.load(s) as z:
                done.update(z["paths"].tolist())
        except Exception as e:
            print(f"warning: skipping unreadable shard {s.name}: {e}", file=sys.stderr)
    failed = load_json(d / "failed.json", {})
    found = discover(root, recurse=not a.no_recurse)
    todo = [p for p in found if p not in done and (a.retry_failed or p not in failed)]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(found)} images found, {len(done)} already indexed, {len(todo)} to do.", flush=True)
    if not todo:
        return

    emb = Embedder(a.model, a.pretrained)
    pre = emb.preprocess

    def prep(rel):
        try:
            return rel, pre(load_image(os.path.join(root, rel))), None
        except Exception as e:  # corrupt, unsupported, online-only and unreadable...
            return rel, None, f"{type(e).__name__}: {e}"[:200]

    t0, n_done = time.time(), 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for start in range(0, len(todo), a.chunk):
            chunk = todo[start: start + a.chunk]
            ok_paths, vecs = [], []
            loaded = list(ex.map(prep, chunk))
            good = [(p, t) for p, t, err in loaded if t is not None]
            for p, t, err in loaded:
                if err:
                    failed[p] = err
            for i in range(0, len(good), a.batch):
                part = good[i: i + a.batch]
                vecs.append(emb.images([t for _, t in part]))
                ok_paths += [p for p, _ in part]
            if ok_paths:
                tmp = d / "wip_shard.npz"  # not matched by the shard_*.npz loader
                np.savez(tmp, paths=np.array(ok_paths), emb=np.concatenate(vecs).astype(np.float16))
                final = d / f"shard_{int(time.time() * 1000)}.npz"
                for attempt in range(40):  # Dropbox may briefly lock the new file
                    try:
                        os.replace(tmp, final)
                        break
                    except PermissionError:
                        if attempt == 39:
                            raise
                        time.sleep(0.5)
            save_json(d / "failed.json", failed)
            n_done += len(chunk)
            rate = n_done / (time.time() - t0)
            eta = (len(todo) - n_done) / rate if rate else 0
            print(f"  {n_done}/{len(todo)}  {rate:.1f} img/s  ETA {eta / 60:.1f} min  failed so far: {len(failed)}", flush=True)
    print(f"Done. Index in {d}")


# -------------------------------------------------------------------- search

def contact_sheet(root, rows, out_png, cols=6, cell=230):
    from PIL import ImageDraw
    n = len(rows)
    nrows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, nrows * (cell + 18)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (rel, score) in enumerate(rows):
        x, y = (i % cols) * cell, (i // cols) * (cell + 18)
        try:
            im = load_image(os.path.join(root, rel))
            im.thumbnail((cell - 6, cell - 6))
            sheet.paste(im, (x + 3, y + 3))
        except Exception:
            pass
        draw.text((x + 4, y + cell), f"{i + 1}  {score:.3f}", fill=(220, 220, 220))
    sheet.save(out_png)


def write_html(root, rows, title, out_html):
    cells = []
    for rel, score in rows:
        src = "../" + quote(rel, safe="/")
        cells.append(
            f'<figure><a href="{src}" target="_blank"><img loading="lazy" src="{src}"></a>'
            f'<figcaption>{score:.3f} &middot; {html.escape(rel)}</figcaption></figure>')
    page = (
        '<!doctype html><meta charset="utf-8"><title>%s</title>'
        "<style>body{background:#181818;color:#ddd;font:13px system-ui;margin:16px}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}"
        "figure{margin:0}img{width:100%%;height:220px;object-fit:contain;background:#222}"
        "figcaption{font-size:11px;word-break:break-all;opacity:.7;padding-top:2px}</style>"
        "<h2>%s</h2><main>%s</main>" % (html.escape(title), html.escape(title), "".join(cells)))
    Path(out_html).write_text(page, encoding="utf-8")


def cmd_search(a):
    root = Path(a.root)
    paths, emb = load_index(root)
    idx = {p: i for i, p in enumerate(paths)}
    score = np.zeros(len(paths), dtype=np.float32)
    label = []

    tags = None
    if a.tag:
        tags = load_json(index_dir(root) / "tags.json", None)
        if tags is None:
            sys.exit("No tags yet. Run:  local_index.py tag <library>")

    embedder = None
    if a.query or a.avoid:
        embedder = Embedder(a.model, a.pretrained)
    for q in a.query:
        score += emb @ embedder.query(q)
        label.append(q)
    for q in a.avoid:
        score -= 0.5 * (emb @ embedder.query(q))
        label.append("not " + q)
    for like in a.like:
        p = Path(like)
        rel = os.path.relpath(p, root).replace("\\", "/") if p.is_absolute() else like.replace("\\", "/")
        if rel not in idx:
            sys.exit(f"--like: {rel} is not in the index")
        score += emb @ emb[idx[rel]]
        label.append("like " + rel)
    if not label and not a.tag:
        sys.exit("Give at least one query, --like or --tag.")

    mask = np.ones(len(paths), dtype=bool)
    if a.folder:
        pre = a.folder.replace("\\", "/").strip("/") + "/"
        mask &= np.array([p.startswith(pre) for p in paths])
    if a.tag:
        label.append("tag " + "+".join(a.tag))
        tagp = np.zeros(len(paths), dtype=np.float32)
        for i, p in enumerate(paths):
            hits = {lab: pr for _, lab, pr in tags.get(p, [])}
            if all(t in hits for t in a.tag):
                tagp[i] = min(hits[t] for t in a.tag)
        mask &= tagp > 0
        score = score + tagp if (a.query or a.like or a.avoid) else tagp

    score = np.where(mask, score, -np.inf)
    order = np.argsort(-score)
    rows = [(paths[i], float(score[i])) for i in order[: a.n] if np.isfinite(score[i]) and score[i] >= a.min_score]
    title = " + ".join(label)
    for i, (rel, sc) in enumerate(rows, 1):
        print(f"{i:3d}  {sc:6.3f}  {rel}")
    if not rows:
        print("No matches.")
        return
    slug = "".join(c if c.isalnum() else "_" for c in title)[:60]
    out_html = Path(root) / DB_DIR / f"search_{slug}.html"
    write_html(root, rows, title, out_html)
    print(f"\nPage: {out_html}")
    if a.sheet:
        contact_sheet(root, rows[: a.sheet_max], a.sheet)
        print(f"Sheet: {a.sheet}")
    if a.open:
        webbrowser.open(out_html.as_uri())


# ----------------------------------------------------------------------- tag

def cmd_tag(a):
    root = Path(a.root)
    paths, emb = load_index(root)
    vocab = load_json(a.vocab, None)
    if not vocab:
        sys.exit(f"Could not read vocabulary {a.vocab}")
    embedder = Embedder(a.model, a.pretrained)
    out = {p: [] for p in paths}
    for group, g in vocab["groups"].items():
        labels = list(g["labels"])
        prompts = [g["labels"][k] for k in labels] + list(g.get("background", []))
        text = embedder.texts(prompts)
        logits = embedder.scale * (emb @ text.T)
        logits -= logits.max(axis=1, keepdims=True)
        prob = np.exp(logits)
        prob /= prob.sum(axis=1, keepdims=True)
        thr, mx = g.get("threshold", 0.25), g.get("max", 2)
        # Softmax alone over-assigns (some label always "wins"). For multi-label
        # groups also require the image to rank in the label's top fraction of
        # the whole library, which bounds how common any one tag can be.
        cut = np.zeros(len(labels))
        if g.get("mode") == "multi":
            raw = emb @ text[: len(labels)].T
            cut = np.quantile(raw, 1 - g.get("top_fraction", 0.15), axis=0)
        else:
            raw = None
        for i, p in enumerate(paths):
            top = np.argsort(-prob[i, : len(labels)])[:mx]
            for j in top:
                if prob[i, j] >= thr and (raw is None or raw[i, j] >= cut[j]):
                    out[p].append([group, labels[j], round(float(prob[i, j]), 3)])
    d = index_dir(root)
    save_json(d / "tags.json", out)
    groups = list(vocab["groups"])
    with open(d / "tags.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["path", *groups])
        for p in paths:
            w.writerow([p] + ["; ".join(l for g, l, _ in out[p] if g == grp) for grp in groups])
    counts = {}
    for tgs in out.values():
        for g, l, _ in tgs:
            counts[(g, l)] = counts.get((g, l), 0) + 1
    print(f"Tagged {len(paths)} images -> {d / 'tags.json'} and tags.csv\nLabel counts:")
    for (g, l), c in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"  {g:7s} {l:22s} {c}")


# ---------------------------------------------------------------------- main

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Local CLIP index for an image folder (no API).")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--pretrained", default=DEFAULT_PRETRAINED)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="embed images (resumable)")
    p.add_argument("root")
    p.add_argument("--no-recurse", action="store_true", help="only the files directly in root")
    p.add_argument("--limit", type=int, default=0, help="stop after N new images (0 = all)")
    p.add_argument("--chunk", type=int, default=256, help="images per saved shard")
    p.add_argument("--batch", type=int, default=64, help="images per GPU batch")
    p.add_argument("--workers", type=int, default=8, help="image-decoding threads")
    p.add_argument("--retry-failed", action="store_true")
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser("search", help="text / example / tag search")
    p.add_argument("root")
    p.add_argument("query", nargs="*", help="text concepts, e.g. spiral")
    p.add_argument("--avoid", action="append", default=[], help="push down this concept")
    p.add_argument("--like", action="append", default=[], help="an indexed image to find more of")
    p.add_argument("--tag", action="append", default=[], help="require a tag label (needs tag run)")
    p.add_argument("--folder", help="limit to a sub-folder, e.g. Posters")
    p.add_argument("-n", type=int, default=60)
    p.add_argument("--min-score", type=float, default=-1e9)
    p.add_argument("--sheet", help="also write a PNG contact sheet here")
    p.add_argument("--sheet-max", type=int, default=48)
    p.add_argument("--open", action="store_true", help="open the result page")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("tag", help="zero-shot keyword tags from a vocabulary")
    p.add_argument("root")
    p.add_argument("--vocab", default=str(VOCAB_FILE))
    p.set_defaults(fn=cmd_tag)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
