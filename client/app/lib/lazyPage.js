import React from "react";

/*
  Pages are code-split, so visiting one fetches a chunk. Two things go wrong
  with that, and neither used to recover.

  A deploy renames every chunk. A tab that was open across it holds the old
  index.html, asks for a file that is no longer on the server, and gets an
  error or an HTML fallback -- and because `React.lazy` remembers a rejected
  import, the page stays broken for as long as the tab lives. On a wall
  screen, which nobody ever reloads, that is for good.

  A dropped request is the same class of failure with a different cure: it
  succeeds on a second ask.

  So: retry, and if the chunk is genuinely not there any more, reload the
  page once to pick up the new index.html. Once, because a chunk that is
  missing from a bad deploy would otherwise reload forever.
*/

export const RELOAD_KEY = "sqldesk:chunk-reload";

/** How long a reload counts for, so a still-broken build does not loop. */
export const RELOAD_WINDOW = 30 * 1000;

const CHUNK_ERROR =
  /Loading chunk|Loading CSS chunk|ChunkLoadError|dynamically imported module|Importing a module script failed|error loading dynamically imported module/i;

export function isChunkLoadError(error) {
  if (!error) {
    return false;
  }
  if (error.name === "ChunkLoadError" || error.code === "CSS_CHUNK_LOAD_FAILED") {
    return true;
  }
  return CHUNK_ERROR.test(String(error.message || error));
}

function reloadedRecently(storage, now) {
  try {
    const at = Number(storage.getItem(RELOAD_KEY));
    return !!at && now - at < RELOAD_WINDOW;
  } catch (err) {
    // Private mode, or storage turned off. Treat it as "not reloaded yet": a
    // single reload is the behaviour we want, and we cannot do better blind.
    return false;
  }
}

function recordReload(storage, now) {
  try {
    storage.setItem(RELOAD_KEY, String(now));
  } catch (err) {
    // Nothing to do -- see above.
  }
}

/**
 * Wraps a dynamic import so it is retried, and a stale chunk reloads the page.
 *
 * @param {() => Promise<any>} load the `() => import(...)` to call
 * @param {object} [options] seams for the tests
 */
export function retryImport(load, options = {}) {
  const {
    attempts = 2,
    delay = 500,
    wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    storage = typeof window !== "undefined" ? window.sessionStorage : null,
    reload = () => window.location.reload(),
    now = () => Date.now(),
  } = options;

  function attempt(left) {
    return load().catch((error) => {
      if (left > 0) {
        return wait(delay).then(() => attempt(left - 1));
      }
      if (isChunkLoadError(error) && storage && !reloadedRecently(storage, now())) {
        recordReload(storage, now());
        reload();
        // The reload is not instant and React would render the rejection in
        // the meantime; a promise that never settles leaves the spinner up
        // until the page goes away.
        return new Promise(() => {});
      }
      throw error;
    });
  }

  return attempt(attempts);
}

/** `React.lazy` for a page: same call, but it survives a deploy. */
export default function lazyPage(load, options = undefined) {
  return React.lazy(() => retryImport(load, options));
}
