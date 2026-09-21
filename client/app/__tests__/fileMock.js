/*
  Webpack turns an imported image or font into a URL. Jest has no loader for
  one, so it tries to parse the SVG as JavaScript and the whole suite fails on
  the first `<`. Anything that imports an asset -- the dashboard header, by way
  of the logo -- needs this to be testable at all.

  Mapped before the `@/` alias in package.json, because the first matching
  pattern wins and `^@/(.*)` would otherwise send it to the real file.
*/
module.exports = "test-file-stub";
