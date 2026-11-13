import React from "react";
import enzyme from "enzyme";
import getOptions from "./getOptions";
import Renderer from "./Renderer";
import { savedOrder } from "./utils";

/*
  Clicking a header sorts a table in the browser and nowhere else. Export as
  image showed the rows sorted; the Slack picture of the same dashboard,
  drawn by the server, showed them in the query's order. The order on screen
  is now saved with the picture and handed back as `sortBy`, where the table
  starts.
*/
const columns = [
  { name: "toggle", type: "integer" },
  { name: "requests", type: "integer" },
];
const rows = [
  { toggle: 1, requests: 10 },
  { toggle: 2, requests: 30 },
  { toggle: 3, requests: 20 },
];

function shown(wrapper: any) {
  return wrapper.find("tbody tr.ant-table-row").map((row: any) => Number(row.find("td").first().text()));
}

function mount(sortBy?: any) {
  const options = getOptions(sortBy ? { sortBy } : {}, { columns });
  return enzyme.mount(<Renderer data={{ columns, rows }} options={options} />);
}

describe("a table's starting order", () => {
  test("is the query's own when nothing was saved", () => {
    expect(shown(mount())).toEqual([1, 2, 3]);
  });

  test("is the saved one when there is one", () => {
    expect(shown(mount([{ name: "requests", direction: "descend" }]))).toEqual([2, 3, 1]);
  });

  test("says what it is, for the page to keep with a picture", () => {
    const wrapper = mount([{ name: "requests", direction: "ascend" }]);
    expect(JSON.parse(wrapper.find(".table-visualization-container").prop("data-table-order"))).toEqual([
      { name: "requests", direction: "ascend" },
    ]);
  });

  test("ignores an order naming a column the table does not have", () => {
    expect(savedOrder([{ name: "gone", direction: "ascend" }], columns)).toEqual([]);
    expect(savedOrder([{ name: "requests", direction: "sideways" }], columns)).toEqual([]);
    expect(savedOrder("requests", columns)).toEqual([]);
  });
});
