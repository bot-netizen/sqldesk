"""
Build the index the site's search box reads.

Every section of every guide page, every release, and every blog post, as a
list of small records: which page, which heading, where it lands, and the
words under it. The site is static -- there is no server to ask -- so the
whole index goes to the browser the first time somebody opens search, and the
matching happens there.

    python3 docs/tools/search.py

Writes docs/assets/search.json, which git ignores: like the blog, it is built
from the pages, locally for a preview and by the docs workflow for the site.
Run it after blog.py, or the posts are not in it.

Standard library only, so the test that holds it to the pages can run in the
backend suite without installing anything.
"""

import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(DOCS, "assets", "search.json")

sys.path.insert(0, HERE)
from chrome import PAGES  # noqa: E402

HEADING = re.compile(r'<h([23])\s[^>]*?id="([^"]+)"[^>]*>(.*?)</h\1>', re.S)
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")
DROP = re.compile(r"<(script|style|svg)\b.*?</\1>", re.S)


def text(fragment):
    """What a reader sees: no markup, no scripts, one space between words."""
    return SPACE.sub(" ", html.unescape(TAG.sub(" ", DROP.sub(" ", fragment)))).strip()


def _between(page, start, end):
    """The part of a page that is its content, not its frame."""
    if start not in page:
        return ""
    inner = page.split(start, 1)[1]
    return inner.split(end, 1)[0] if end in inner else inner


def sections(content, url, title):
    """
    One record for the page itself and one per heading that can be linked to.

    A heading without an id is folded into the section above it: a result has
    to land somewhere, and the top of a long page is not somewhere.
    """
    found = list(HEADING.finditer(content))
    lede = content[: found[0].start()] if found else content
    records = [{"p": title, "h": "", "u": url, "t": text(lede)}]
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(content)
        records.append(
            {
                "p": title,
                "h": text(match.group(3)),
                "u": "{}#{}".format(url, match.group(2)),
                "t": text(content[match.end() : end]),
            }
        )
    return records


def build(docs=DOCS):
    records = []

    for filename, title, _section in PAGES:
        if filename.startswith("../"):
            continue
        page = open(os.path.join(docs, "guide", filename), encoding="utf-8").read()
        content = _between(page, '<main class="doc-body">', '<div class="doc-next">')
        records.extend(sections(content, "guide/" + filename, title))

    releases = os.path.join(docs, "releases.html")
    if os.path.exists(releases):
        page = open(releases, encoding="utf-8").read()
        records.extend(sections(_between(page, "<main", "</main>"), "releases.html", "Releases"))

    blog = os.path.join(docs, "blog")
    if os.path.isdir(blog):
        for filename in sorted(os.listdir(blog)):
            if not filename.endswith(".html") or filename == "index.html":
                continue
            page = open(os.path.join(blog, filename), encoding="utf-8").read()
            title = text(_between(page, "<h1", "</h1>").split(">", 1)[-1]) or filename
            records.extend(sections(_between(page, "<article>", "</article>"), "blog/" + filename, title))

    # A record with nothing to match on is a result nobody can find.
    return [record for record in records if record["h"] or record["t"]]


def main():
    records = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))
    print("indexed {} sections in {} bytes".format(len(records), os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
