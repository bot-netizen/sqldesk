import { marked } from "marked";

/*
  Markdown, for textbox widgets and for the descriptions on queries and
  visualizations.

  This replaced `markdown@0.5.0`, which was last released in 2013 and quietly
  refused most of what anybody writing a section on a dashboard would type:
  a table came out as literal pipes in a paragraph, a ```sql fence lost both
  its newlines and its language, and `~~`, task lists and bare URLs were left
  as text.

  `breaks: true` -- a single newline is a line break. CommonMark says it is
  not, and the old library agreed with CommonMark, but nobody typing into a
  box five rows tall means "join these two lines into a paragraph".

  Pinned to marked 4, the last line that ships CommonJS. Later ones are ESM
  only, and nothing in this repository transforms `node_modules` for jest:
  the two packages each carry a file-relative `.babelrc` and there is no root
  babel config, so adding one to reach a single dependency would put a new
  config in the path of both builds. Version 4 has every feature this swap
  was for.

  Raw HTML passes through, which is the single biggest thing this gives an
  author: a two-column section, a coloured callout, an image at a chosen
  width. What makes that safe is not this file -- it is `HtmlContent`, which
  runs every string here through DOMPurify before it reaches the DOM. Nothing
  should render the output of this function any other way.
*/
marked.setOptions({
  gfm: true,
  breaks: true,
  // No `id` on headings. Nothing links to them, and a dashboard of textboxes
  // that all start "## Overview" would put the same id in the document
  // several times over.
  headerIds: false,
  // Obfuscating mailto links against 2004's spam harvesters, at the cost of
  // entity soup in the markup. Off, and deprecated upstream.
  mangle: false,
});

export default function toHtml(text) {
  return marked.parse(text === null || text === undefined ? "" : String(text));
}
