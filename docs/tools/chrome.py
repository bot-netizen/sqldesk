"""
Rewrite the chrome around every page in docs/guide.

The nav, the header, the footer and the previous/next links are the same on
twelve pages, so they are generated rather than copied: adding a page or
changing the reading order is one edit to PAGES below, followed by

    python3 docs/tools/chrome.py

Each page's *body* is its own and is read back out of the file, so running
this never touches what a page says -- only the frame around it. Run it
twice and the second run changes nothing; that is the test at the bottom.
"""

import os

ICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'%3E%3Cg fill='none' "
    "stroke='%230a7c93' stroke-width='4'%3E%3Ccircle cx='60' cy='60' r='55.5'/%3E%3C/g%3E%3Cg fill='%230a7c93'%3E"
    "%3Crect x='34' y='70' width='12' height='15' rx='1.5'/%3E%3Crect x='48' y='56' width='12' height='29' rx='1.5'/%3E"
    "%3Crect x='62' y='63' width='12' height='22' rx='1.5'/%3E%3Crect x='76' y='50' width='12' height='35' rx='1.5'/%3E"
    "%3Crect x='30' y='84' width='62' height='5.5' rx='2.75'/%3E%3C/g%3E%3C/svg%3E"
)

BRAND = """<svg viewBox="0 0 120 120" aria-hidden="true">
        <g fill="none" stroke="currentColor" stroke-width="4"><circle cx="60" cy="60" r="55.5"/></g>
        <g fill="currentColor">
          <rect x="34" y="70" width="12" height="15" rx="1.5"/><rect x="48" y="56" width="12" height="29" rx="1.5"/>
          <rect x="62" y="63" width="12" height="22" rx="1.5"/><rect x="76" y="50" width="12" height="35" rx="1.5"/>
          <rect x="30" y="84" width="62" height="5.5" rx="2.75"/>
        </g>
      </svg>"""

# The header links, in one place. The site's own pages are one directory
# apart -- index.html at the root, guide/ and blog/ below it -- so each link
# is rendered with the prefix its page needs rather than written out twice
# and left to drift. The nav has drifted before; that is why this exists.
#
# (file, label, hide on narrow screens)
SITE_NAV = [
    ("index.html", "Overview", False),
    ("guide/overview.html", "Docs", False),
    ("blog/index.html", "Blog", False),
    ("releases.html", "Releases", False),
]

#: Pages that live at the root and keep their own stylesheet, so only their
#: header nav is rewritten.
TOP_LEVEL = ["index.html", "releases.html"]


def site_nav(prefix, current):
    """
    The header links. `current` is the SITE_NAV file the page belongs to, so
    a guide page marks Docs and a post marks Blog.
    """
    out = []
    for href, label, hide_sm in SITE_NAV:
        cls = ' class="hide-sm"' if hide_sm else ""
        mark = ' aria-current="page"' if href == current else ""
        out.append('      <a href="{}{}"{}{}>{}</a>'.format(prefix, href, cls, mark, label))
    out.append('      <a href="https://github.com/bot-netizen/sqldesk">GitHub</a>')
    out.append(
        """      <button class="theme-toggle" type="button" data-theme-toggle
              aria-label="Switch to dark mode" title="Switch to dark mode">
        <svg class="moon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M13.5 9.6A5.6 5.6 0 0 1 6.4 2.5a5.7 5.7 0 1 0 7.1 7.1Z"/>
        </svg>
        <svg class="sun" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
             stroke-linecap="round" aria-hidden="true">
          <circle cx="8" cy="8" r="3.1"/>
          <path d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1M12.9 12.9l-1.1-1.1M4.2 4.2 3.1 3.1"/>
        </svg>
      </button>"""
    )
    return "\n".join(out)


def rewrite_topbar_nav(path, prefix, current):
    """
    Replace what is between <nav> and </nav> in a page's top bar.

    Surgical on purpose: these pages carry their own inline stylesheet and
    their own content, and the only thing that has to agree across all of
    them is this list of links.
    """
    html = open(path).read()
    opened = html.index('<header class="topbar">')
    start = html.index("<nav>", opened) + len("<nav>")
    end = html.index("</nav>", start)
    updated = html[:start] + "\n" + site_nav(prefix, current) + "\n    " + html[end:]
    if updated != html:
        open(path, "w").write(updated)
        return True
    return False


def _slug(text):
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    out = out.strip("-")
    # An id may begin with a digit in HTML but not in a CSS selector, so
    # "0.6: your warehouse" would produce an anchor the browser can jump to
    # and no stylesheet or script can ever select. Prefixed rather than
    # renumbered, so the heading keeps its own words.
    if out and out[0].isdigit():
        out = "s-" + out
    return out


# (file, title, section) -- the order is the reading order.
PAGES = [
    ("overview.html", "Overview", "Start here"),
    ("concepts.html", "Concepts", "Start here"),
    ("architecture.html", "Architecture", "Start here"),
    ("connectors.html", "Data sources", "Using SQLDesk"),
    ("queries.html", "Queries and parameters", "Using SQLDesk"),
    ("visualizations.html", "Visualizations", "Using SQLDesk"),
    ("dashboards.html", "Dashboards and textboxes", "Using SQLDesk"),
    ("streams.html", "Streams", "Using SQLDesk"),
    ("alerts.html", "Alerts", "Using SQLDesk"),
    ("mcp.html", "MCP", "AI"),
    ("administration.html", "Administration", "Running it"),
    ("deploying.html", "Deploying", "Running it"),
    ("../releases.html", "Releases", "Reference"),
]


def nav(current):
    out, seen = [], None
    for href, title, section in PAGES:
        if section != seen:
            out.append("      <h4>{}</h4>".format(section))
            seen = section
        mark = ' aria-current="page"' if href == current else ""
        out.append('      <a href="{}"{}>{}</a>'.format(href, mark, title))
    return "\n".join(out)


def neighbours(current):
    names = [p[0] for p in PAGES]
    i = names.index(current)
    links = []
    if i:
        links.append('<a class="btn btn-ghost" href="{}">&larr; {}</a>'.format(PAGES[i - 1][0], PAGES[i - 1][1]))
    if i + 1 < len(PAGES):
        links.append('<a class="btn btn-primary" href="{}">{} &rarr;</a>'.format(PAGES[i + 1][0], PAGES[i + 1][1]))
    return '<div class="doc-next">{}</div>'.format("".join(links)) if links else ""


BODY_OPEN = '<main class="doc-body">'
BODY_CLOSE = "</main>"
NEXT_OPEN = '<div class="doc-next">'


def _read(path):
    """The page's own content: what sits between <main> and the next/prev links."""
    html = open(path).read()
    inner = html.split(BODY_OPEN, 1)[1].rsplit(BODY_CLOSE, 1)[0]
    # The next/prev row is generated too, so drop it before putting it back.
    if NEXT_OPEN in inner:
        inner = inner.rsplit(NEXT_OPEN, 1)[0]
    return inner.strip("\n")


def _description(path):
    html = open(path).read()
    return html.split('<meta name="description" content="', 1)[1].split('">', 1)[0]


def render(filename, description, body):
    title = dict((p[0], p[1]) for p in PAGES)[filename]
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} \u2014 SQLDesk docs</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title} \u2014 SQLDesk docs">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:url" content="https://sqldesk.org/guide/{filename}">
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
{nav_site}
    </nav>
  </div>
</header>

<div class="wrap doc-layout">
  <nav class="doc-nav" aria-label="Documentation">
{nav}
  </nav>
  <main class="doc-body">
{body}
{next}
  </main>
</div>

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
""".format(
        title=title,
        filename=filename,
        description=description,
        icon=ICON,
        brand=BRAND,
        nav=nav(filename),
        nav_site=site_nav("../", "guide/overview.html"),
        body=body,
        next=neighbours(filename),
    )


def main():
    docs = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    changed = []

    # The guide, whose whole frame is generated. An entry reaching outside
    # guide/ is a sidebar link to a page that keeps its own frame -- it
    # belongs in the list so it appears in the contents, not in this loop,
    # which would look for a guide body it does not have.
    for filename, _title, _section in PAGES:
        if filename.startswith("../"):
            continue
        path = os.path.join(docs, "guide", filename)
        before = open(path).read()
        after = render(filename, _description(path), _read(path))
        if after != before:
            open(path, "w").write(after)
            changed.append("guide/" + filename)

    # The root pages, where only the header links are ours. The blog is
    # built whole from Markdown by blog.py, header included.
    for filename in TOP_LEVEL:
        path = os.path.join(docs, filename)
        if os.path.exists(path) and rewrite_topbar_nav(path, "", filename):
            changed.append(filename)

    print("rewrote {} page(s)".format(len(changed)))
    for name in changed:
        print("  " + name)


if __name__ == "__main__":
    main()
