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

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'%3E%3Cg fill='none' "
        "stroke='%230a7c93' stroke-width='4'%3E%3Ccircle cx='60' cy='60' r='55.5'/%3E%3C/g%3E%3Cg fill='%230a7c93'%3E"
        "%3Crect x='34' y='70' width='12' height='15' rx='1.5'/%3E%3Crect x='48' y='56' width='12' height='29' rx='1.5'/%3E"
        "%3Crect x='62' y='63' width='12' height='22' rx='1.5'/%3E%3Crect x='76' y='50' width='12' height='35' rx='1.5'/%3E"
        "%3Crect x='30' y='84' width='62' height='5.5' rx='2.75'/%3E%3C/g%3E%3C/svg%3E")

BRAND = """<svg viewBox="0 0 120 120" aria-hidden="true">
        <g fill="none" stroke="currentColor" stroke-width="4"><circle cx="60" cy="60" r="55.5"/></g>
        <g fill="currentColor">
          <rect x="34" y="70" width="12" height="15" rx="1.5"/><rect x="48" y="56" width="12" height="29" rx="1.5"/>
          <rect x="62" y="63" width="12" height="22" rx="1.5"/><rect x="76" y="50" width="12" height="35" rx="1.5"/>
          <rect x="30" y="84" width="62" height="5.5" rx="2.75"/>
        </g>
      </svg>"""

# (file, title, section) -- the order is the reading order.
PAGES = [
    ("overview.html", "Overview", "Start here"),
    ("concepts.html", "Concepts", "Start here"),
    ("architecture.html", "Architecture", "Start here"),
    ("connectors.html", "Data sources", "Using SQLDesk"),
    ("queries.html", "Queries and parameters", "Using SQLDesk"),
    ("visualizations.html", "Visualizations", "Using SQLDesk"),
    ("dashboards.html", "Dashboards and textboxes", "Using SQLDesk"),
    ("alerts.html", "Alerts", "Using SQLDesk"),
    ("mcp.html", "MCP", "AI"),
    ("administration.html", "Administration", "Running it"),
    ("deploying.html", "Deploying", "Running it"),
    ("releases.html", "Releases", "Reference"),
]


def nav(current):
    out, seen = [], None
    for href, title, section in PAGES:
        if section != seen:
            out.append('      <h4>{}</h4>'.format(section))
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
<link rel="icon" href="{icon}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400..700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<link rel="stylesheet" href="../assets/site.css">
</head>
<body>

<header class="topbar">
  <div class="wrap topbar-in">
    <a class="brand" href="../index.html">
      {brand}
      SQLDesk
    </a>
    <nav>
      <a href="../index.html">Overview</a>
      <a href="../why.html">Why SQLDesk</a>
      <a href="../performance.html" class="hide-sm">Performance</a>
      <a href="../roadmap.html">Roadmap</a>
      <a href="overview.html" aria-current="page">Docs</a>
      <a href="https://github.com/bot-netizen/sqldesk">GitHub</a>
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
       <a href="releases.html">Releases</a> &nbsp;&middot;&nbsp;
       <a href="https://github.com/bot-netizen/sqldesk">Source</a> &nbsp;&middot;&nbsp;
       <a href="https://github.com/bot-netizen/sqldesk/blob/main/LICENSE">Apache 2.0</a></p>
  </div>
</footer>

</body>
</html>
""".format(title=title, description=description, icon=ICON, brand=BRAND,
           nav=nav(filename), body=body, next=neighbours(filename))


def main():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guide")
    changed = []
    for filename, _title, _section in PAGES:
        path = os.path.normpath(os.path.join(here, filename))
        before = open(path).read()
        after = render(filename, _description(path), _read(path))
        if after != before:
            open(path, "w").write(after)
            changed.append(filename)
    print("rewrote {} of {} pages".format(len(changed), len(PAGES)))
    for name in changed:
        print("  " + name)


if __name__ == "__main__":
    main()
