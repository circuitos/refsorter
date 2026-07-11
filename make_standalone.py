#!/usr/bin/env python3
"""Build the single-file version of catalog_refs.py.

Reads the repo modules plus templates/wiki.html and writes dist/catalog_refs.py,
one self-contained script with no local imports. That file is the one to copy
to the Desktop and run directly:

    python make_standalone.py
    (then copy dist/catalog_refs.py wherever you like)
"""

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dist" / "catalog_refs.py"

TEMPLATE_SENTINEL = "WIKI_TEMPLATE = None  # the standalone build inlines templates/wiki.html here"
SPLICE_COMMENT = (
    "# Imported below the settings on purpose: make_standalone.py splices each\n"
    "# module's source in at its import line, keeping the config at the top.\n"
)
_LOCAL_IMPORT = re.compile(r"^from (record_schema|cleaning|artists|viewer|sorter) import .*\n", re.M)
_DOCSTRING = re.compile(r'\A("""|\'\'\')(?s:.*?)\1\n+')


def module_body(name):
    """A module's source with its docstring and local imports removed."""
    src = (HERE / (name + ".py")).read_text(encoding="utf-8")
    src = _DOCSTRING.sub("", src)
    src = _LOCAL_IMPORT.sub("", src)
    return src.strip("\n")


def banner(label):
    return "# " + "-" * 75 + " " + label + "\n\n"


def main():
    template = (HERE / "templates" / "wiki.html").read_text(encoding="utf-8")
    if '"""' in template or template.endswith("\\"):
        raise SystemExit("templates/wiki.html cannot be inlined as a raw triple-quoted string.")

    viewer_src = module_body("viewer")
    if TEMPLATE_SENTINEL not in viewer_src:
        raise SystemExit("viewer.py is missing the WIKI_TEMPLATE sentinel line.")
    viewer_src = viewer_src.replace(TEMPLATE_SENTINEL, 'WIKI_TEMPLATE = r"""' + template + '"""')

    out = (HERE / "catalog_refs.py").read_text(encoding="utf-8")
    out = out.replace(SPLICE_COMMENT, "")
    for line, body in [
        ("from record_schema import SYSTEM, RECORD_TOOL\n", banner("record schema") + module_body("record_schema")),
        ("from cleaning import clean_record\n", banner("record cleaning") + module_body("cleaning")),
        ("from artists import ensure_artists, folder_hints\n", banner("artist database") + module_body("artists")),
        ("from viewer import write_wiki\n", banner("wiki viewer") + viewer_src),
        ("from sorter import run_sort, undo_sort\n", banner("painter-folder sorter") + module_body("sorter")),
    ]:
        if out.count(line) != 1:
            raise SystemExit("expected exactly one line %r in catalog_refs.py" % line)
        out = out.replace(line, body + "\n\n")

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("wrote %s (%d lines)" % (OUT.relative_to(HERE), out.count("\n")))


if __name__ == "__main__":
    main()
