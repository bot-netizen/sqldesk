import getOptions from "./getOptions";

/*
  The funnel gained a drawn shape beside the bars it has always been. The
  shape is an option, so the thing worth pinning down is that it defaults to
  what every funnel saved before now already looks like: a funnel that
  silently changed shape on upgrade would be a worse bug than one that never
  gained the option at all.
*/

const columns = [{ name: "step" }, { name: "visits" }];

describe("the funnel's shape option", () => {
  test("a funnel saved before the option existed still draws as bars", () => {
    const saved = { stepCol: { colName: "step" }, valueCol: { colName: "visits" } };
    expect(getOptions(saved, { columns }).shape).toBe("bars");
  });

  test("a new funnel draws as bars", () => {
    expect(getOptions({}, { columns }).shape).toBe("bars");
  });

  test("the drawn shape is kept when it is chosen", () => {
    expect(getOptions({ shape: "funnel" }, { columns }).shape).toBe("funnel");
  });

  test("anything else falls back to bars rather than drawing nothing", () => {
    // Options can arrive through the API, where nothing checks them.
    ["", null, "pie", 7, {}].forEach((shape) => {
      expect(getOptions({ shape }, { columns }).shape).toBe("bars");
    });
  });

  test("the shape does not disturb the rest of the settings", () => {
    const saved = {
      shape: "funnel",
      stepCol: { colName: "step", displayAs: "Stage" },
      valueCol: { colName: "visits", displayAs: "People" },
      itemsLimit: 5,
    };
    const options = getOptions(saved, { columns });
    expect(options.stepCol.displayAs).toBe("Stage");
    expect(options.valueCol.displayAs).toBe("People");
    expect(options.itemsLimit).toBe(5);
  });
});
