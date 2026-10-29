# The blog

Every post is one Markdown file in this folder. Commit it, push, and the
docs site publishes it: its own page, a line on the Blog page, and a place in
every post's side rail. There is nothing else to edit.

## Writing a post

Make a file here named the way you want the address to read. It must use
lowercase letters, digits and hyphens: `what-changed-in-0-7.md` is published
at `blog/what-changed-in-0-7.html`.

Start it with this block, then write the post in Markdown underneath:

```markdown
---
title: What changed in 0.7
date: 2026-11-02
summary: >-
  One or two sentences for the Blog page, under the title.
---

The first paragraph of the post.

## A section

Every `##` heading goes into the post's "On this page" list.
```

`title`, `date` (as `YYYY-MM-DD`) and `summary` are required. Newer dates
come first. If a value contains `: `, put it in quotes or use `>-` as above:
`summary: 0.7: faster` is not valid, while `summary: "0.7: faster"` is.

Optional:

| Key | What it does |
|---|---|
| `lede` | The paragraph under the post's title. Defaults to `summary`. |
| `description` | What search engines and link previews show. Defaults to `summary`. |
| `next` | A button at the end of the post, as `label:` and `link:` on the lines below it. |
| `draft: true` | Keeps the post off the site until you remove it. |

## Links and images

- Other pages on the site: start at the site root, such as
  `[Deploying](/guide/deploying.html)` or `[Releases](/releases.html)`.
- Other posts: just the file name with `.html`, such as `[the first post](sqldesk-and-what-it-is-for.html)`.
- Images: put them in `blog/images/` and write `![What it shows](images/chart.png)`.

Tables, code blocks and ~~strikethrough~~ work as in GitHub. So does raw
HTML, for the rare thing Markdown cannot say.

## When it goes live

A push that changes this folder, on `main` or a `release/` branch, publishes
the site from that branch. Put a post on the branch the site is published
from: the current release branch while a release is being tested, otherwise
`main`.

If a post cannot be built (no title, a bad date, a file name that cannot be
an address), the publish stops, the site stays as it was, and the workflow's
log names the file and what is wrong with it.

## Previewing

```bash
pip install markdown-it-py pyyaml
python3 docs/tools/blog.py
```

Then open `docs/blog/index.html`. That folder is built output, and git
ignores it.
