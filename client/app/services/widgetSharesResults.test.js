import Widget from "./widget";
import { resetInFlight } from "./inFlightResults";

/*
  The question this file answers is the one the dashboard actually asks: put
  several visualizations of one query on a dashboard, load it, and how many
  requests go out?

  It used to be one per widget. Each downloaded the same rows and each spent
  most of a second building its own QueryResult from them -- measured at 960ms
  in QueryResult.update() on a 20k-row result, on the main thread, three times
  over for three widgets.

  What decides whether two widgets can share is `resultKey`, so that is what is
  pinned here: same question, same key; different question, different key.
*/

jest.mock("@sqldesk/viz/lib", () => ({
  registeredVisualizations: { CHART: { name: "Chart" }, TABLE: { name: "Table" } },
  preloadVisualization: () => {},
}));

function widget({ queryId = 7, type = "CHART", parameters = {}, applyAutoLimit = false } = {}) {
  const w = new Widget({
    id: Math.random(),
    visualization: {
      id: Math.random(),
      type,
      query: {
        id: queryId,
        name: "a query",
        query: "select 1",
        options: { parameters: [], apply_auto_limit: applyAutoLimit },
      },
    },
    options: { position: { col: 0, row: 0, sizeX: 4, sizeY: 4 } },
  });
  // Stand in for the parameter machinery, which reads from the URL.
  w.getQuery().getParameters = () => ({ getExecutionValues: () => parameters });
  return w;
}

beforeEach(() => resetInFlight());

describe("widgets that want the same result", () => {
  test("two visualizations of one query ask the same question", () => {
    const chart = widget({ type: "CHART" });
    const table = widget({ type: "TABLE" });

    expect(table.resultKey(0)).toBe(chart.resultKey(0));
  });

  test("a whole dashboard of them still asks one question", () => {
    const keys = ["CHART", "TABLE", "CHART", "TABLE", "CHART"].map((type) => widget({ type }).resultKey(0));

    expect(new Set(keys).size).toBe(1);
  });

  test("different queries ask different questions", () => {
    expect(widget({ queryId: 7 }).resultKey(0)).not.toBe(widget({ queryId: 8 }).resultKey(0));
  });

  test("the same query with different parameter values does not share", () => {
    // The whole point of a parameter is that it changes the result.
    const north = widget({ parameters: { region: "North" } });
    const south = widget({ parameters: { region: "South" } });

    expect(south.resultKey(0)).not.toBe(north.resultKey(0));
  });

  test("the auto limit is part of the question", () => {
    const limited = widget({ applyAutoLimit: true });
    const whole = widget({ applyAutoLimit: false });

    expect(limited.resultKey(0)).not.toBe(whole.resultKey(0));
  });

  test("asking for a different freshness does not share", () => {
    // max_age 0 runs the query; -1 takes the newest stored result. A widget
    // that wants one must not be given the other.
    const w = widget();

    expect(w.resultKey(0)).not.toBe(w.resultKey(-1));
    expect(w.resultKey(0)).not.toBe(w.resultKey(undefined));
  });

  test("two widgets told to load the same result id share it", () => {
    // What a live dashboard does: the server names the newest result and
    // every widget on that query is sent to fetch the same one.
    const a = widget();
    const b = widget();

    expect(b.resultKey(undefined, 4321)).toBe(a.resultKey(undefined, 4321));
    expect(a.resultKey(undefined, 4321)).not.toBe(a.resultKey(undefined, 9999));
  });

  test("a widget with nothing to show shares nothing", () => {
    // A textbox has no query; it must never be handed somebody else's result.
    const textbox = new Widget({ id: 1, text: "hello", options: {} });

    expect(textbox.resultKey(0)).toBeNull();
  });
});
