import { PlainListFetcher } from "./ItemsFetcher";
import Paginator from "./Paginator";
import Sorter from "./Sorter";

/*
  Searching a plain list did nothing. `updateSearch` reports `{ search: true }`
  and this fetcher only went back to the server for `tags` or `sorting`, so the
  search change fell through to the branch that re-pages whatever was already
  held -- unfiltered. The comment above that condition said "tags or search",
  which is presumably how it survived: the intent was written down and the code
  did not match it.

  Alerts is the list that showed it. Its endpoint returns every alert with no
  `q` to pass, so the term had nowhere to go even once the refetch happened.
*/

const ALERTS = [
  { id: 1, name: "Revenue dropped", query: { name: "Daily revenue" } },
  { id: 2, name: "Signups flat", query: { name: "New accounts" } },
  { id: 3, name: "Disk nearly full", query: { name: "Host capacity" } },
  { id: 4, name: "Checkout errors", query: { name: "Daily revenue" } },
];

function matches(alert, term) {
  const fields = [alert.name, alert.query && alert.query.name];
  return fields.some((field) => typeof field === "string" && field.toLowerCase().includes(term));
}

function build({ withMatches = true, itemsPerPage = 20 } = {}) {
  const doRequest = jest.fn(() => Promise.resolve(ALERTS));
  const fetcher = new PlainListFetcher({
    doRequest,
    getRequest: () => ({}),
    processResults: (items) => items,
    matches: withMatches ? matches : undefined,
  });

  const state = (searchTerm = "") => ({
    paginator: new Paginator({ page: 1, itemsPerPage, totalCount: ALERTS.length }),
    sorter: new Sorter({ orderByField: "name" }),
    searchTerm,
    selectedTags: [],
  });

  // Whatever a list does first: the full load, with no changes flagged.
  const load = () => fetcher.fetch(null, state(), {});

  return { fetcher, doRequest, state, load };
}

const names = (result) => result.results.map((item) => item.name);

describe("PlainListFetcher searching", () => {
  it("filters the items it already holds", async () => {
    const { fetcher, state, load } = build();
    await load();

    const result = await fetcher.fetch({ search: true }, state("signups"), {});

    expect(names(result)).toEqual(["Signups flat"]);
  });

  it("searches every item rather than the page in front of you", async () => {
    // Two per page, and the only match is on the second. A filter that ran
    // over the current page would find nothing -- which is the behaviour the
    // module comment calls worse than having no control at all.
    const { fetcher, state, load } = build({ itemsPerPage: 2 });
    await load();

    const result = await fetcher.fetch({ search: true }, state("disk"), {});

    expect(names(result)).toEqual(["Disk nearly full"]);
  });

  it("counts the matches, so the pager knows how many pages there are", async () => {
    const { fetcher, state, load } = build();
    await load();

    const result = await fetcher.fetch({ search: true }, state("daily revenue"), {});

    expect(result.count).toBe(2);
    expect(names(result).sort()).toEqual(["Checkout errors", "Revenue dropped"]);
  });

  it("matches what the alert watches, not only what it is called", async () => {
    const { fetcher, state, load } = build();
    await load();

    const result = await fetcher.fetch({ search: true }, state("host capacity"), {});

    expect(names(result)).toEqual(["Disk nearly full"]);
  });

  it("ignores case and surrounding space", async () => {
    const { fetcher, state, load } = build();
    await load();

    const result = await fetcher.fetch({ search: true }, state("  SIGNUPS  "), {});

    expect(names(result)).toEqual(["Signups flat"]);
  });

  it("gives everything back when the term is cleared", async () => {
    const { fetcher, state, load } = build();
    await load();

    const result = await fetcher.fetch({ search: true }, state(""), {});

    expect(result.count).toBe(ALERTS.length);
  });

  it("does not ask the server again to answer a search it can answer itself", async () => {
    const { fetcher, doRequest, state, load } = build();
    await load();
    expect(doRequest).toHaveBeenCalledTimes(1);

    await fetcher.fetch({ search: true }, state("signups"), {});

    expect(doRequest).toHaveBeenCalledTimes(1);
  });

  it("still goes to the server for a list whose endpoint does the searching", async () => {
    // No `matches`: the endpoint takes `q`, so the term belongs to it. This is
    // every list that worked before, and it has to keep working.
    const { fetcher, doRequest, state, load } = build({ withMatches: false });
    await load();

    await fetcher.fetch({ search: true }, state("signups"), {});

    expect(doRequest).toHaveBeenCalledTimes(2);
  });

  it("passes the term to an endpoint that takes one", async () => {
    const getRequest = jest.fn(() => ({}));
    const fetcher = new PlainListFetcher({
      getRequest,
      doRequest: () => Promise.resolve(ALERTS),
      processResults: (items) => items,
    });

    await fetcher.fetch(
      { search: true },
      {
        paginator: new Paginator({ page: 1, itemsPerPage: 20 }),
        sorter: new Sorter({ orderByField: "name" }),
        searchTerm: "signups",
        selectedTags: [],
      },
      {}
    );

    expect(getRequest).toHaveBeenCalledWith(expect.objectContaining({ q: "signups" }), expect.anything());
  });
});
