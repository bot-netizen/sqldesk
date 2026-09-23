/*
  How fresh a result has to be, named rather than numbered.

  The API takes one number, `max_age`: 0 runs the query, -1 returns the newest
  stored result without running anything, and N returns a stored result if one
  is younger than N seconds. Nothing wrong with that -- but the client had
  nine places computing or defaulting it, and had started using `undefined` to
  mean three unrelated things:

  - "a page is loading, whatever result this object already holds will do"
    (`Query.prepareQueryResultExecution`),
  - "the Refresh button, so run it" (`Widget.load`, where `force` turned
    `undefined` into 0),
  - "ignore me, I am passing a result id instead" (the live dashboard).

  Two shipped bugs came out of that (0230dcdd, 6385d6a3), both of the same
  shape: a caller meant one of those and a reader down the chain took it for
  another, and the dashboard quietly kept showing the first result it ever
  loaded.

  So a caller names its intent and this file decides the number. There are
  five intents and every one of them is a sentence about what the reader
  wants, not an age.
*/

/**
 * @typedef {object} Freshness
 * @property {string} name          Which intent this is; for tests and logs.
 * @property {number|undefined} maxAge   What goes to the API as `max_age`.
 * @property {number|null} resultId A specific result to fetch, instead.
 * @property {boolean} reuseLoaded  Whether a result already in hand will do.
 */

function freshness(name, { maxAge = undefined, resultId = null, reuseLoaded = false }) {
  return { name, maxAge, resultId, reuseLoaded };
}

/**
 * Opening a page. Whatever result is already to hand will do, and only a
 * widget that has none fetches anything.
 */
export const onPageLoad = () => freshness("page-load", { reuseLoaded: true });

/** Run the query now: the Refresh button, and new parameter values. */
export const runNow = () => freshness("run-now", { maxAge: 0 });

/**
 * The newest result the server has stored, without running anything.
 *
 * What the query page opens on, and what a public link's live dashboard asks
 * for -- its key may not read results by id.
 */
export const newestStored = () => freshness("newest-stored", { maxAge: -1 });

/** Run it, unless somebody else ran it within the last `seconds`. */
export const noOlderThan = (seconds) => freshness("no-older-than", { maxAge: seconds });

/**
 * Exactly this result, by id: a live dashboard, told which one is newest.
 *
 * It names no age at all, which is the third meaning `undefined` used to
 * carry. Here it is a separate intent with a separate field, so nothing
 * downstream has to guess which one was meant.
 */
export const thisResult = (resultId) => freshness("this-result", { resultId });

/**
 * An auto-refresh tick.
 *
 * Other open tabs' results should do -- that is the point of accepting an age
 * at all -- but this tab's own last result is just under one interval old
 * when its timer fires again, so accepting a whole interval reused it and the
 * dashboard refreshed every other tick at best. Half the interval still lets
 * tabs share a run.
 */
export const onAutoRefresh = (refreshRate) => noOlderThan(Math.floor(refreshRate / 2));
