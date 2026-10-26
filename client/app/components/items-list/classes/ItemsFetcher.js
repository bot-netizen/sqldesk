import { identity, isFunction, isNil, isString } from "lodash";

class ItemsFetcher {
  _getRequest(state, context) {
    return this._originalGetRequest({}, context);
  }

  // Anything the endpoint returns beyond results/count is carried through as
  // `meta`, so a page can read response-level figures (a failing count, say)
  // without every list endpoint growing its own plumbing.
  _processResults({ results, count, ...meta }, state, context) {
    return {
      results: this._originalProcessResults(results, context),
      count,
      meta,
    };
  }

  constructor({ getRequest, doRequest, processResults }) {
    this._originalGetRequest = isFunction(getRequest) ? getRequest : identity;
    this._originalDoRequest = doRequest;
    this._originalProcessResults = isFunction(processResults) ? processResults : identity;
  }

  fetch(changes, state, context) {
    const request = this._getRequest(state, context);
    return this._originalDoRequest(request, context).then((data) => this._processResults(data, state, context));
  }
}

// For endpoints that return just an array with items; sorting and pagination
// is performed on client
export class PlainListFetcher extends ItemsFetcher {
  _allItems = [];

  /*
    `matches` makes search work on a list whose endpoint has no `q`.

    Searching a plain list did nothing at all: `updateSearch` reports
    `{ search: true }`, and the condition in `fetch` below only went back to the
    server for `tags` or `sorting` -- so a search change re-paged the same
    unfiltered items. The comment on it claimed otherwise, which is presumably
    why it went unnoticed.

    Where the whole list is already in the browser, filtering it here is both
    the cheapest fix and an honest one: it filters every item rather than the
    page in front of you. A list whose endpoint does support `q` passes no
    `matches` and goes back to the server, as before.
  */
  constructor({ matches, ...rest }) {
    super(rest);
    this._matches = isFunction(matches) ? matches : null;
  }

  _pageOf({ paginator, searchTerm }) {
    const term = isString(searchTerm) ? searchTerm.trim().toLowerCase() : "";
    const items =
      this._matches && term !== "" ? this._allItems.filter((item) => this._matches(item, term)) : this._allItems;

    // `count` is what the source feeds back into the paginator's total, so a
    // filtered list gets the right number of pages. Searching resets to page
    // one (updateSearch does it), so the current page cannot be left stranded
    // past the end of a narrower list.
    return {
      results: paginator.getItemsForPage(items),
      count: items.length,
      allResults: items,
    };
  }

  _getRequest({ searchTerm, selectedTags }, context) {
    return this._originalGetRequest(
      {
        q: isString(searchTerm) && searchTerm !== "" ? searchTerm : undefined,
        tags: selectedTags,
      },
      context
    );
  }

  _processResults(data, state, context) {
    this._allItems = state.sorter.sort(this._originalProcessResults(data, context));
    return this._pageOf(state);
  }

  fetch(changes, state, context) {
    // Only go back to the server for things the server decides. A search it
    // cannot answer is handled here instead.
    const searchNeedsServer = changes && changes.search && !this._matches;
    if (isNil(changes) || changes.tags || changes.sorting || searchNeedsServer) {
      return super.fetch(changes, state, context);
    }
    return Promise.resolve(this._pageOf(state));
  }
}

// For endpoints that support server-side pagination (return object with
// items for current page and total items count)
export class PaginatedListFetcher extends ItemsFetcher {
  _getRequest({ paginator, sorter, searchTerm, selectedTags }, context) {
    return this._originalGetRequest(
      {
        page: paginator.page,
        page_size: paginator.itemsPerPage,
        order: sorter.compiled,
        q: isString(searchTerm) && searchTerm !== "" ? searchTerm : undefined,
        tags: selectedTags,
      },
      context
    );
  }
}
