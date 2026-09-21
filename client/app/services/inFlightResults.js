/*
  One fetch for one result, however many widgets want it.

  Every widget builds its own Query and fetches its own result, so two
  visualizations of the same query each download it and each turn it into a
  QueryResult of their own -- for identical data. Measured on a 20k-row,
  eight-column result (3.3 MB):

    JSON.parse                14 ms
    QueryResult.update()     960 ms, on the main thread

  So three widgets on one query was about 2.9 seconds of blocked interface and
  10 MB transferred instead of 3.3.

  Requests that are identical *and overlap in time* are answered by a single
  fetch. Overlapping is the normal case: a dashboard load and a live refresh
  both walk their widgets in one synchronous pass, so the second widget asks
  while the first is still waiting.

  This shares work; it does not cache results. The entry is dropped the moment
  the request settles, so the next refresh always starts a new one -- which is
  what keeps a dashboard honest about how fresh its data is.
*/

const inFlight = new Map();

/**
 * Run `start`, or hand back the request already running for this key.
 *
 * A null key means "do not share" -- for callers that cannot say what they
 * are asking for, and so cannot know that somebody else is asking the same.
 */
export default function shareInFlight(key, start) {
  if (key === null || key === undefined) {
    return start();
  }

  const existing = inFlight.get(key);
  if (existing) {
    return existing;
  }

  const queryResult = start();
  inFlight.set(key, queryResult);

  // Dropped on failure as well as success: a request that failed must not be
  // handed to the next widget that asks, or one bad refresh would stick.
  const done = () => {
    if (inFlight.get(key) === queryResult) {
      inFlight.delete(key);
    }
  };
  queryResult.toPromise().then(done, done);

  return queryResult;
}

/** How many requests are in flight. For tests and for measuring. */
export function inFlightCount() {
  return inFlight.size;
}

/** Forget everything in flight. For tests. */
export function resetInFlight() {
  inFlight.clear();
}
