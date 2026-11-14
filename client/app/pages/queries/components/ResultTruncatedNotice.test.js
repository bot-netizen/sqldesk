import React from "react";
import { mount } from "enzyme";
import ResultTruncatedNotice, { truncationMessage } from "./ResultTruncatedNotice";

/*
  A cut-short result used to say so in a tooltip on an orange icon, worded for
  Databricks. It says so above the rows now: how many, why, and what to do.
*/
describe("a result that is not all of the result", () => {
  test("cut at the size limit says the limit, that the query was stopped, and how to change it", () => {
    const { title, detail } = truncationMessage(454751, { reason: "size", limit_mb: 100 });
    expect(title).toContain("454,751 rows");
    expect(title).toContain("100 MB");
    expect(detail).toContain("stopped on the data source");
    expect(detail).toContain("LIMIT");
    expect(detail).toContain("queryResults.maxMB");
  });

  test("cut by the data source itself says that instead", () => {
    const { title } = truncationMessage(20000, null);
    expect(title).toContain("20,000 rows");
    expect(title).toContain("data source returned no more");
  });

  test("is shown, not hidden in a tooltip", () => {
    const wrapper = mount(<ResultTruncatedNotice rowCount={10} truncation={{ reason: "size", limit_mb: 100 }} />);
    expect(wrapper.find('[data-test="ResultTruncatedNotice"]').first().text()).toContain("Showing the first 10 rows");
  });
});
