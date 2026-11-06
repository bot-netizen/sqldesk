import fixture from "./__demo-fixture.json";
import registeredVisualizations from "./registeredVisualizations";
import "./lazyComponents";

/*
  Every demo visualization, asked whether its stored options mean anything.

  The options in `sqldesk/demo/content.py` are written by hand against
  twenty-two different option schemas, and a wrong key does not fail loudly:
  `getOptions` merges what it is given over its defaults, so a misspelt
  column name becomes a chart with nothing on it, or a render that throws
  where the dashboard catches it and says only "something on this page did
  not work".

  So each one is put through its own `getOptions` with the columns the demo
  query really returns, and asked to name a column that exists.
*/
const entries = fixture;

/** Every column name a visualization could legitimately point at. */
function columnNames(entry) {
  return entry.columns.map(one => one.name);
}

/** The option values that look like a column reference. */
function referencedColumns(options) {
  const found = [];
  const walk = (value, key) => {
    if (typeof value === "string" && /column|col$|colname|^column$/i.test(key)) {
      found.push(value);
    } else if (Array.isArray(value)) {
      value.forEach(one => walk(one, key));
    } else if (value && typeof value === "object") {
      Object.entries(value).forEach(([k, v]) => walk(v, k));
    }
  };
  Object.entries(options || {}).forEach(([k, v]) => walk(v, k));
  return found;
}

describe("the demo's visualization options", () => {
  test("the fixture covers every registered type", () => {
    const registered = Object.keys(registeredVisualizations);
    const demonstrated = new Set(entries.map(one => one.type));

    expect(registered.filter(one => !demonstrated.has(one))).toEqual([]);
  });

  entries.forEach(entry => {
    describe(`${entry.type} — ${entry.name}`, () => {
      test("names only columns its query returns", () => {
        const available = columnNames(entry);
        const named = referencedColumns(entry.options);

        named.forEach(one => {
          expect(available).toContain(one);
        });
      });

      test("sets only keys the visualization reads", () => {
        /*
          The check that was missing. `getOptions` merges what it is given
          over its defaults, so an invented key is simply carried along --
          the chart never reads it, falls back to nothing, and fails
          somewhere far away.

          The choropleth was given `countryCodeColumn` where it reads
          `keyColumn`. It joined nothing, had no bounds to fit, and the
          dashboard died on "Invalid LatLng object: (NaN, NaN)" with nothing
          pointing back here.

          Anything `getOptions({})` does not produce is a key this
          visualization has no opinion about.
        */
        const visualization = registeredVisualizations[entry.type];
        const data = { columns: entry.columns, rows: entry.rows || [] };
        const known = Object.keys(visualization.getOptions({}, data));

        const unknown = Object.keys(entry.options).filter(one => !known.includes(one));
        expect(unknown).toEqual([]);
      });

      test("its own getOptions accepts them", () => {
        const visualization = registeredVisualizations[entry.type];
        expect(visualization).toBeDefined();

        const data = { columns: entry.columns, rows: entry.rows || [] };
        const options = visualization.getOptions(entry.options, data);

        expect(options).toBeTruthy();
      });
    });
  });
});

