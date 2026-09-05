#!/usr/bin/env python3
"""Turn bookmarklet/export.js into javascript: URLs you can save as bookmarks.

Writes:
    bookmarklet/export-all.bookmarklet.txt      every conversation
    bookmarklet/export-current.bookmarklet.txt  only the open conversation
"""

import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent / "bookmarklet"
SOURCE = ROOT / "export.js"

# Characters left unencoded so the result stays somewhat readable. '#' and '%'
# are deliberately encoded: '#' would start a URL fragment, '%' would be
# misread as an escape.
SAFE = "!'()*+,-./:;<=>?@[]^_`{|}~ &$\""


def compact(js: str) -> str:
    js = re.sub(r"/\*[\s\S]*?\*/", "", js)
    lines = [line.strip() for line in js.splitlines()]
    return " ".join(line for line in lines if line)


def main():
    code = compact(SOURCE.read_text())
    variants = {
        "export-all": code,
        "export-current": "window.__CLAUDE_EXPORT_MODE='current';" + code,
    }
    for name, body in variants.items():
        url = "javascript:" + quote(body, safe=SAFE)
        (ROOT / f"{name}.bookmarklet.txt").write_text(url + "\n")
        print(f"wrote bookmarklet/{name}.bookmarklet.txt ({len(url)} chars)")


if __name__ == "__main__":
    main()
