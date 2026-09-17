import React from "react";
import { mount } from "enzyme";
import ScheduledQueriesList from "./ScheduledQueriesList";
import HomeCounters from "./HomeCounters";

const QUERY = {
  id: 7,
  name: "Nightly revenue",
  data_source: "Warehouse",
  runtime: 92.5,
  result_bytes: 5 * 1024 * 1024,
  schedule: { interval: null, cron: "0 2 * * *" },
};

describe("ScheduledQueriesList", () => {
  it("shows the name, data source, runtime, size and schedule", () => {
    const text = mount(<ScheduledQueriesList queries={[QUERY]} />).text();

    expect(text).toContain("Nightly revenue");
    expect(text).toContain("Warehouse");
    expect(text).toContain("5 MB");
    expect(text).toContain("0 2 * * *");
  });

  it("links the query name", () => {
    const wrapper = mount(<ScheduledQueriesList queries={[QUERY]} />);

    expect(wrapper.find('a[href="queries/7"]')).not.toHaveLength(0);
  });

  it("says a query has not run rather than showing a zero runtime", () => {
    // null runtime formatted as a duration reads "0 seconds", which says the
    // query is instant when in fact nothing is known about it.
    const text = mount(<ScheduledQueriesList queries={[{ ...QUERY, runtime: null, result_bytes: null }]} />).text();

    expect(text).toContain("not yet run");
    expect(text).not.toContain("0 seconds");
  });

  it("explains itself when there is nothing scheduled", () => {
    const text = mount(<ScheduledQueriesList queries={[]} />).text();

    expect(text).toContain("refresh schedule");
  });

  it("shows nothing but a placeholder while loading", () => {
    const wrapper = mount(<ScheduledQueriesList queries={[]} loading />);

    expect(wrapper.find(".ant-skeleton")).not.toHaveLength(0);
    expect(wrapper.text()).not.toContain("refresh schedule");
  });
});

describe("HomeCounters", () => {
  const counters = {
    queries: 12,
    dashboards: 3,
    scheduled_queries: 5,
    alerts: 2,
    result_storage_bytes: 3 * 1024 * 1024 * 1024,
  };

  it("shows every count", () => {
    const text = mount(<HomeCounters counters={counters} />).text();

    expect(text).toContain("12");
    expect(text).toContain("Queries");
    expect(text).toContain("Dashboards");
    expect(text).toContain("Scheduled");
    expect(text).toContain("Alerts");
  });

  it("shows storage as a size with its unit", () => {
    const text = mount(<HomeCounters counters={counters} />).text();

    expect(text).toContain("3");
    expect(text).toContain("GB");
  });

  it("renders without counters rather than throwing", () => {
    // The page loads the counters after it renders, and drops them silently if
    // the request fails -- so null is a state this actually reaches.
    expect(() => mount(<HomeCounters counters={null} loading />)).not.toThrow();
  });
});
