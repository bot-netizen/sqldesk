import React from "react";
import { mount } from "enzyme";

import AlertHistory from "./AlertHistory";

/*
  The page could already say where an alert is now and when it last moved.
  What it could not say is whether this is the first time or the sixth, which
  is usually why somebody opened it.
*/

const fire = (overrides = {}) => ({
  state: "triggered",
  value: "412",
  notified: true,
  created_at: "2026-10-27T10:00:00Z",
  ...overrides,
});

describe("AlertHistory", () => {
  it("lists what happened, in the order it was given", () => {
    const wrapper = mount(
      <AlertHistory
        history={[fire({ state: "ok", value: "120" }), fire({ state: "triggered", value: "412" })]}
        fires24h={1}
      />
    );

    const states = wrapper.find(".alert-history-state").map((n) => n.text());
    expect(states).toEqual(["ok", "triggered"]);
  });

  it("shows the number the alert fired on", () => {
    // "It fired" is a fact. "It fired at 412" is the one worth being woken for.
    const wrapper = mount(<AlertHistory history={[fire({ value: "412" })]} fires24h={1} />);

    expect(wrapper.find(".alert-history-value").text()).toBe("412");
  });

  it("leaves the value out rather than printing nothing where there is none", () => {
    // Null is what an unreadable query gives, which is the same reason the
    // state went unknown. An empty cell says that better than "null" does.
    const wrapper = mount(<AlertHistory history={[fire({ state: "unknown", value: null })]} fires24h={0} />);

    expect(wrapper.find(".alert-history-value").exists()).toBe(false);
  });

  it("counts the fires above the list", () => {
    const wrapper = mount(<AlertHistory history={[fire(), fire()]} fires24h={2} />);

    expect(wrapper.find(".alert-history-count").text()).toContain("2 times in the last 24 hours");
  });

  it("says time, not times, for one", () => {
    const wrapper = mount(<AlertHistory history={[fire()]} fires24h={1} />);

    expect(wrapper.find(".alert-history-count").text()).toContain("1 time in the last 24 hours");
  });

  it("marks a fire nobody was told about", () => {
    // A muted alert still changes state. Showing it the same as a sent one
    // would have somebody hunting for a message that was never sent.
    const wrapper = mount(<AlertHistory history={[fire({ notified: false })]} fires24h={1} />);

    expect(wrapper.find(".alert-history-silent").exists()).toBe(true);
  });

  it("does not mark a recovery as unsent, because recoveries are not fires", () => {
    const wrapper = mount(<AlertHistory history={[fire({ state: "ok", notified: false })]} fires24h={0} />);

    expect(wrapper.find(".alert-history-silent").exists()).toBe(false);
  });

  it("a new alert reads as empty rather than broken", () => {
    const wrapper = mount(<AlertHistory history={[]} fires24h={0} />);

    expect(wrapper.find(".alert-history-empty").exists()).toBe(true);
    expect(wrapper.find(".alert-history-list").exists()).toBe(false);
  });

  it("says nothing about a count of zero", () => {
    // A line reading "fired 0 times" is worse than no line.
    const wrapper = mount(<AlertHistory history={[fire({ state: "ok" })]} fires24h={0} />);

    expect(wrapper.find(".alert-history-count").exists()).toBe(false);
  });
});
