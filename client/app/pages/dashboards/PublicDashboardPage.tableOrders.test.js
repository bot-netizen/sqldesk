import { applyTableOrders } from "./PublicDashboardPage";

/*
  A picture drawn for Slack starts each table in the order the person it is
  sent for last saw it in -- by widget id, tables only.
*/
describe("the order a picture's tables are drawn in", () => {
  const order = [{ name: "requests", direction: "descend" }];

  function widgets() {
    return [
      { id: 31, visualization: { type: "TABLE", options: { itemsPerPage: 25 } } },
      { id: 32, visualization: { type: "CHART", options: {} } },
      { id: 33, visualization: { type: "TABLE", options: {} } },
      { id: 34, text: "a text box" },
    ];
  }

  test("is the saved one, for the table it was saved for", () => {
    const all = widgets();
    applyTableOrders(all, { 31: order, 32: order });

    expect(all[0].visualization.options).toEqual({ itemsPerPage: 25, sortBy: order });
    expect(all[1].visualization.options.sortBy).toBeUndefined();
    expect(all[2].visualization.options.sortBy).toBeUndefined();
  });

  test("is set once, so the page redraws nothing on its next render", () => {
    const all = widgets();
    applyTableOrders(all, { 31: order });
    const first = all[0].visualization.options;
    applyTableOrders(all, { 31: order });

    expect(all[0].visualization.options).toBe(first);
  });

  test("leaves everything alone with nothing saved", () => {
    const all = widgets();
    applyTableOrders(all, undefined);

    expect(all[0].visualization.options).toEqual({ itemsPerPage: 25 });
  });
});
