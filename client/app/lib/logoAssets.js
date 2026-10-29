/*
  A data source or destination logo is a file named after the type, and
  `TypeLogo` draws a tile of initials when there is no file. That part works --
  but it works by *asking for the file first* and waiting for the 404, so every
  type without a logo logs a failed request on every page that lists it. Kafka
  did it, Mimir does it, and the next runner somebody registers will too.

  Webpack already enumerates this folder at build time (`requireImages` in
  config/index.js emits every image under it), so the set of logos that exist
  is knowable without asking the network. Checking against it means a missing
  logo goes straight to its tile: no request, no 404, and nothing to remember
  when adding a type.

  Dropping a real logo into the folder is still all it takes to get one -- the
  list is rebuilt from the directory, not maintained here.
*/

function knownLogos() {
  try {
    // Relative keys, "./db-logos/mimir.png", normalised to "db-logos/mimir.png".
    const ctx = require.context("@/assets/images/", true, /\.(png|jpe?g|gif|svg)$/);
    return new Set(ctx.keys().map((key) => key.replace(/^\.\//, "")));
  } catch (err) {
    // No webpack to ask -- jest, or any build without require.context. Treat
    // nothing as known-missing, which is exactly how this behaved before.
    return null;
  }
}

const KNOWN = knownLogos();

/** `/static/images/db-logos/pg.png` and `static/images/destinations/slack.png` both. */
const UNDER_IMAGES = /(?:^|\/)static\/images\/(.+)$/;

/**
 * Whether this is a logo we can see is not there, so it should not be fetched.
 *
 * Deliberately false for anything uncertain: a path that is not one of ours, or
 * a build where the folder listing is unavailable. Guessing wrong in that
 * direction costs a 404; guessing wrong the other way hides a logo that exists.
 *
 * @param {string|null} src the URL a caller is about to put in an <img>
 * @param {Set<string>|null} [known] the build-time listing; a seam for the tests
 */
export default function isMissingLogo(src, known = KNOWN) {
  if (!src || !known) {
    return false;
  }
  const match = UNDER_IMAGES.exec(src);
  if (!match) {
    return false;
  }
  return !known.has(match[1]);
}
