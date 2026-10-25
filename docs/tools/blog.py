"""
Build the blog from the Markdown files in blog/.

A post is one file in the repository's top-level blog/ directory. Commit it
and the docs workflow publishes it: its own page, a line in the listing, and
a place in every post's left rail. Nothing else is edited by hand, because
the listing and the rails are exactly the things that drifted when they were.

    pip install markdown-it-py pyyaml
    python3 docs/tools/blog.py

That writes docs/blog/, which git ignores: the Markdown is the record and the
HTML is built from it, locally for a preview and in CI for the site. How to
write a post is in blog/README.md.

A post that cannot be built -- no title, a date that is not a date, a file
name that cannot be an address -- stops the build with the file named,
rather than publishing a page with a hole in it.
"""

import argparse
import datetime
import html
import os
import re
import shutil
import sys

import yaml
from chrome import BRAND, ICON, _slug, site_nav
from markdown_it import MarkdownIt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SOURCE = os.path.join(ROOT, "blog")
OUT = os.path.join(ROOT, "docs", "blog")

#: Files in blog/ that are about the blog rather than in it.
NOT_POSTS = {"README.md"}

#: The file name is the address, so it has to be one.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

LISTING_LEDE = (
    "Notes on building SQLDesk &mdash; what shipped, what it cost to run, and the things that\n"
    "    turned out to be wrong once real data touched them."
)
LISTING_DESCRIPTION = "Notes on building SQLDesk: what shipped, what it cost, and what turned out to be wrong."

# CommonMark, with raw HTML allowed for the odd thing Markdown cannot say,
# and the two extensions posts actually use.
markdown = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])


class PostError(Exception):
    pass


def _front_matter(text, name):
    """Split `---` YAML `---` from the body."""
    if not text.startswith("---"):
        raise PostError("{}: starts without front matter; the first line must be ---".format(name))
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        raise PostError("{}: the front matter is never closed with a line of ---".format(name))
    try:
        meta = yaml.safe_load(parts[0][3:]) or {}
    except yaml.YAMLError as e:
        raise PostError("{}: the front matter is not valid YAML ({})".format(name, e))
    if not isinstance(meta, dict):
        raise PostError("{}: the front matter must be `key: value` lines".format(name))
    return meta, parts[1].split("\n", 1)[1] if "\n" in parts[1] else ""


def _date(value, name):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise PostError("{}: date must look like 2026-09-26, not {!r}".format(name, value))


def _plain(fragment):
    """Rendered inline HTML as one line of text, for a meta description."""
    text = re.sub(r"<[^>]+>", "", fragment)
    return " ".join(html.unescape(text).split())


def with_heading_ids(body):
    """
    Give each h2 an id, and list them for the right rail.

    Generated rather than written, because a heading whose id does not match
    the link to it is a link that silently goes nowhere.
    """
    entries, used = [], set()

    def number(match):
        text = match.group(1)
        plain = _plain(text)
        ident, n = _slug(plain) or "section", 2
        while ident in used:
            ident, n = "{}-{}".format(_slug(plain) or "section", n), n + 1
        used.add(ident)
        entries.append((ident, plain))
        return '<h2 id="{}">{}</h2>'.format(ident, text)

    return re.sub(r"<h2>(.*?)</h2>", number, body, flags=re.S), entries


def read_post(path):
    name = os.path.basename(path)
    stem = name[: -len(".md")]
    if not NAME.match(stem) or stem == "index":
        raise PostError(
            "{}: the file name becomes the address, so use lowercase letters, digits and hyphens "
            "(and not `index`)".format(name)
        )
    with open(path, encoding="utf-8") as f:
        meta, text = _front_matter(f.read(), name)

    missing = [key for key in ("title", "date", "summary") if not meta.get(key)]
    if missing:
        raise PostError("{}: missing {} in the front matter".format(name, ", ".join(missing)))

    summary = markdown.renderInline(str(meta["summary"]).strip())
    lede = markdown.renderInline(str(meta["lede"]).strip()) if meta.get("lede") else summary
    body, toc = with_heading_ids(markdown.render(text))
    following = meta.get("next") or {}
    if following and not (isinstance(following, dict) and following.get("label") and following.get("link")):
        raise PostError("{}: next needs both a label and a link".format(name))

    return {
        "file": stem + ".html",
        "title": str(meta["title"]).strip(),
        "date": _date(meta["date"], name),
        "summary": summary,
        "lede": lede,
        "description": str(meta.get("description") or "").strip() or _plain(summary),
        "next": following,
        "draft": bool(meta.get("draft")),
        "body": body,
        "toc": toc,
    }


def _shown(day):
    return "{} {}".format(day.day, day.strftime("%B %Y"))


def _head(title, description, og_title, og_type, url):
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="https://sqldesk.org/assets/social-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="SQLDesk: one place for everything you do with data">
<meta property="og:site_name" content="SQLDesk">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://sqldesk.org/assets/social-card.png">
<link rel="icon" href="{icon}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400..700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<link rel="stylesheet" href="../assets/site.css">
<script>document.documentElement.classList.add("js");try{{var t=localStorage.getItem("sqldesk-theme");if(t==="dark")document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
</head>
<body>

<header class="topbar">
  <div class="wrap topbar-in">
    <a class="brand" href="../index.html">
      {brand}
      SQLDesk
    </a>
    <nav>
{nav}
    </nav>
  </div>
</header>
""".format(
        title=html.escape(title),
        description=html.escape(description),
        og_title=html.escape(og_title),
        og_type=og_type,
        url=url,
        icon=ICON,
        brand=BRAND,
        nav=site_nav("../", "blog/index.html"),
    )


FOOT = """
<footer>
  <div class="wrap">
    <p><a href="../index.html">&larr; Back to overview</a> &nbsp;&middot;&nbsp;
       <a href="../releases.html">Releases</a> &nbsp;&middot;&nbsp;
       <a href="https://github.com/bot-netizen/sqldesk">Source</a> &nbsp;&middot;&nbsp;
       <a href="https://github.com/bot-netizen/sqldesk/blob/main/LICENSE">Apache 2.0</a></p>
  </div>
</footer>

<script src="../assets/theme.js" defer></script>
</body>
</html>
"""


def post_nav(posts, current):
    out = ["      <h4>All posts</h4>"]
    for post in posts:
        mark = ' aria-current="page"' if post["file"] == current else ""
        out.append('      <a href="{}"{}>{}'.format(post["file"], mark, html.escape(post["title"])))
        out.append('        <span class="post-nav-when">{}</span>'.format(_shown(post["date"])))
        out.append("      </a>")
    return "\n".join(out)


def site_links(page):
    """
    `/guide/mcp.html` in a post means the site's own page. The site is served
    from a subdirectory (/sqldesk/), where a root-relative link would leave
    it, so those links are made relative to blog/ instead.
    """
    return re.sub(r'(href|src)="/(?!/)', r'\1="../', page)


def render_post(post, posts):
    toc = ""
    if post["toc"]:
        toc = "\n".join(
            ["      <h4>On this page</h4>"]
            + ['      <a href="#{}">{}</a>'.format(ident, html.escape(plain)) for ident, plain in post["toc"]]
        )
    following = ""
    if post["next"]:
        following = '<a class="btn btn-primary" href="{}">{} &rarr;</a>'.format(
            html.escape(post["next"]["link"]), html.escape(post["next"]["label"])
        )
    page = (
        _head(
            post["title"] + " — SQLDesk",
            post["description"],
            post["title"],
            "article",
            "https://sqldesk.org/blog/" + post["file"],
        )
        + """
<div class="wrap post-layout">
  <nav class="post-nav" aria-label="Posts">
{rail}
    </nav>

  <article>
  <div class="post-head">
    <div class="post-meta"><time datetime="{iso}">{shown}</time></div>
    <h1>{title}</h1>
    <p class="lede">{lede}</p>
  </div>

  <div class="post-body">

{body}
  </div>
  </article>

  <nav class="post-toc" aria-label="On this page">
{toc}
    </nav>
</div>

<div class="wrap post-after">
  <div class="doc-next"><a class="btn btn-ghost" href="index.html">&larr; All posts</a>{following}</div>
</div>
""".format(
            rail=post_nav(posts, post["file"]),
            iso=post["date"].isoformat(),
            shown=_shown(post["date"]),
            title=html.escape(post["title"]),
            lede=post["lede"],
            body=post["body"],
            toc=toc,
            following=following,
        )
        + FOOT
    )
    return site_links(page)


def render_listing(posts):
    items = []
    for post in posts:
        items.append(
            """    <li>
      <div class="post-meta"><time datetime="{iso}">{shown}</time></div>
      <h2><a href="{file}">{title}</a></h2>
      <p>{summary}</p>
    </li>""".format(
                iso=post["date"].isoformat(),
                shown=_shown(post["date"]),
                file=post["file"],
                title=html.escape(post["title"]),
                summary=post["summary"],
            )
        )
    page = (
        _head("Blog — SQLDesk", LISTING_DESCRIPTION, "SQLDesk blog", "website", "https://sqldesk.org/blog/")
        + """
<div class="wrap post-layout">
  <nav class="post-nav" aria-label="Posts">
{rail}
    </nav>

  <div>
  <div class="post-head">
    <h1>Blog</h1>
    <p class="lede">{lede}</p>
  </div>

  <ul class="post-list">
{items}
  </ul>
  </div>
</div>
""".format(
            rail=post_nav(posts, "index.html"),
            lede=LISTING_LEDE,
            items="\n".join(items) if items else "    <li><p>Nothing posted yet.</p></li>",
        )
        + FOOT
    )
    return site_links(page)


def build(source, out):
    """Read every post, and write nothing unless all of them read cleanly."""
    posts, errors, assets = [], [], []
    for folder, _dirs, files in os.walk(source):
        for name in sorted(files):
            path = os.path.join(folder, name)
            relative = os.path.relpath(path, source)
            if name in NOT_POSTS and folder == source:
                continue
            if name.endswith(".md") and folder == source:
                try:
                    posts.append(read_post(path))
                except PostError as e:
                    errors.append(str(e))
            elif not name.endswith(".md"):
                # Images and anything else a post links to, kept at the same
                # relative path so `images/chart.png` in a post just works.
                assets.append(relative)

    if errors:
        raise PostError("\n".join(errors))

    published = sorted((p for p in posts if not p["draft"]), key=lambda p: (p["date"], p["title"]), reverse=True)

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    for relative in assets:
        target = os.path.join(out, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(source, relative), target)
    for post in published:
        with open(os.path.join(out, post["file"]), "w", encoding="utf-8") as f:
            f.write(render_post(post, published))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_listing(published))

    return published, [p for p in posts if p["draft"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--source", default=SOURCE, help="the Markdown posts (default: blog/)")
    parser.add_argument("--out", default=OUT, help="where the pages go (default: docs/blog/)")
    args = parser.parse_args()

    try:
        published, drafts = build(args.source, args.out)
    except PostError as e:
        print("The blog was not built:\n" + str(e), file=sys.stderr)
        sys.exit(1)

    where = os.path.relpath(args.out, ROOT)
    print("built {} post(s) into {}".format(len(published), args.out if where.startswith("..") else where))
    for post in published:
        print("  {}  {}".format(post["date"].isoformat(), post["file"]))
    for post in drafts:
        print("  draft, not published: {}".format(post["file"].replace(".html", ".md")))


if __name__ == "__main__":
    main()
