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
type Entry = {
  type: string;
  name: string;
  query: string;
  options: Record<string, any>;
  columns: { name: string; type: string }[];
};

const entries = fixture as Entry[];

/** Every column name a visualization could legitimately point at. */
function columnNames(entry: Entry) {
  return entry.columns.map(one => one.name);
}

/** The option values that look like a column reference. */
function referencedColumns(options: any): string[] {
  const found: string[] = [];
  const walk = (value: any, key: string) => {
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

      test("its own getOptions accepts them", () => {
        const visualization = (registeredVisualizations as any)[entry.type];
        expect(visualization).toBeDefined();

        const data = { columns: entry.columns, rows: entry.rows || [] };
        const options = visualization.getOptions(entry.options, data);

        expect(options).toBeTruthy();
      });
    });
  });
});

