/*
  A tile of initials, in a colour worked out from the name.

  Used where a picture is missing and inventing one would be worse: a data
  source type with no logo file, and a person who has not got a photograph.
  Both want the same two things -- something recognisable at 13 pixels, and
  the same colour every time, so a face in a list is findable by its colour
  before it is read.

  Deterministic rather than random or stored: a colour that changes between
  renders is worse than no colour, and one in the database is a column to
  migrate for something nobody will ever want to set.
*/

// Chosen to sit beside the application's own palette and to stay legible
// under white text.
export const TILE_COLOURS = ["#4b6cb7", "#2e8b7a", "#8a5fbf", "#b5651d", "#3c7d9e", "#9c4668", "#5c7a3f", "#7a5c3f"];

/** The same label always gets the same colour, between renders and reloads. */
export function tileColour(label) {
  let hash = 0;
  const text = String(label || "");
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) % 100000;
  }
  return TILE_COLOURS[hash % TILE_COLOURS.length];
}

/**
 * One or two letters standing in for a name.
 *
 * Two words give their first letters, which is what makes "Ana Flores" read
 * as AF rather than AN. One word gives its first two, because a single
 * letter is not enough to tell two rows apart.
 */
export function initials(label) {
  const words = String(label || "")
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);

  if (words.length === 0) {
    return "?";
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return (words[0][0] + words[1][0]).toUpperCase();
}
