import { keepSelections } from "./VisualizationRenderer";

/*
  Every new result -- a live dashboard's refresh, a streaming query's tick --
  reset each filter to its first value, so a selection lasted until the next
  refresh.
*/
describe("filters across a new result", () => {
  const fresh = [
    { name: "region", values: ["east", "west", "north"], current: "east", multiple: false },
    { name: "item", values: ["bolt", "gasket"], current: ["bolt"], multiple: true },
  ];

  test("a choice still among the values is kept", () => {
    const previous = [
      { name: "region", current: "north" },
      { name: "item", current: ["gasket"] },
    ];

    expect(keepSelections(fresh, previous).map((f) => f.current)).toEqual(["north", ["gasket"]]);
  });

  test("one that has gone falls back to the fresh default", () => {
    const previous = [
      { name: "region", current: "south" },
      { name: "item", current: ["flange", "gasket"] },
    ];

    expect(keepSelections(fresh, previous).map((f) => f.current)).toEqual(["east", ["gasket"]]);
  });

  test("a filter that is new has its default", () => {
    expect(keepSelections(fresh, []).map((f) => f.current)).toEqual(["east", ["bolt"]]);
  });
});
