import registeredVisualizations from "../registeredVisualizations";
import { SHAPES } from "./dataShapes";
import { VARIANTS } from "./optionVariants";

/*
  Every visualization's `getOptions`, against every option the editor offers
  and every awkward result a query can return.

  `getOptions` runs before anything is drawn -- the dashboard calls it to size
  a widget, the editor calls it on every keystroke -- so a throw here takes
  down the page rather than showing an empty chart. It also has to be
  idempotent: the editor feeds its own output straight back in, so an option
  that changes on the second pass makes the editor fight the person using it.
*/

const types = Object.keys(registeredVisualizations).sort();

describe("every visualization's options", () => {
  test("the matrix covers every registered visualization", () => {
    // A new visualization with no variants listed would otherwise be tested
    // by nothing at all and nobody would notice.
    expect(types.length).toBe(22);
    types.forEach((type) => expect(VARIANTS[type]).toBeDefined());
  });

  types.forEach((type) => {
    const config: any = (registeredVisualizations as any)[type];
    const variants = VARIANTS[type] || [{ name: "defaults", options: {} }];

    describe(`${config.name} (${type})`, () => {
      test.each(SHAPES.map((s) => [s.name, s] as const))("survives %s", (_name, shape) => {
        variants.forEach((variant) => {
          const data = { columns: shape.columns, rows: shape.rows };
          let options: any;
          expect(() => {
            options = config.getOptions(variant.options, data);
          }).not.toThrow();
          expect(options).toEqual(expect.any(Object));
        });
      });

      test("reading its own output back gives the same options", () => {
        // The editor does exactly this on every change. An option that keeps
        // moving makes the control it belongs to impossible to use.
        const data = { columns: SHAPES[0].columns, rows: SHAPES[0].rows };
        variants.forEach((variant) => {
          const once = config.getOptions(variant.options, data);
          const twice = config.getOptions(once, data);
          expect(twice).toEqual(once);
        });
      });

      test("options survive being saved and loaded again", () => {
        // Options go to the database as JSON and come back, which loses
        // undefined and turns dates into strings.
        const data = { columns: SHAPES[0].columns, rows: SHAPES[0].rows };
        variants.forEach((variant) => {
          const saved = JSON.parse(JSON.stringify(config.getOptions(variant.options, data)));
          expect(() => config.getOptions(saved, data)).not.toThrow();
          expect(config.getOptions(saved, data)).toEqual(saved);
        });
      });

      test("works with no data at all, which is what a new visualization has", () => {
        variants.forEach((variant) => {
          expect(() => config.getOptions(variant.options, { columns: [], rows: [] })).not.toThrow();
          expect(() => config.getOptions(variant.options, undefined)).not.toThrow();
        });
      });

      test("junk in the saved options does not take the page down", () => {
        // Options can be written through the API, where nothing checks them.
        const data = { columns: SHAPES[0].columns, rows: SHAPES[0].rows };
        const junk = [
          null,
          undefined,
          {},
          { valueColumn: 42, labelColumn: [], thresholds: "nonsense", valueFormat: "nonsense" },
          { valueColumns: "not an array", pathColumns: 7, mappings: "no" },
          { binCount: "lots", visibleDepth: "deep", rowNumber: "first", itemsLimit: -1 },
          { style: 12, mode: {}, shape: null, range: [], countMode: 0, scaleMode: false },
        ];
        junk.forEach((options) => {
          expect(() => config.getOptions(options, data)).not.toThrow();
        });
      });
    });
  });
});
