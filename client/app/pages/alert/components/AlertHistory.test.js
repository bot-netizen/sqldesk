import React from "react";
import { mount } from "enzyme";

import AlertHistory, { firedAt } from "./AlertHistory";

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

describe("AlertHistory, when and where", () => {
  it("says when as a time, not only as 'ago'", () => {
    const wrapper = mount(<AlertHistory history={[fire({ created_at: "2026-11-13T14:32:05Z" })]} fires24h={1} />);

    const when = wrapper.find(".alert-history-when");
    expect(when.prop("dateTime")).toBe("2026-11-13T14:32:05Z");
    // The tests run in Africa/Khartoum (UTC+2): the viewer's own time.
    expect(when.text()).toBe("Fri, 13 Nov 2026, 16:32:05 GMT+2");
    expect(wrapper.find(".alert-history-ago").exists()).toBe(true);
  });

  it("formats a time it cannot read as nothing rather than 'Invalid Date'", () => {
    expect(firedAt("not a date")).toBe("");
  });

  it("says which destinations it went to", () => {
    const wrapper = mount(
      <AlertHistory
        history={[
          fire({
            deliveries: [
              { destination: "Slack #ops", type: "slack_app", ok: true, detail: "Posted to C1 with 1 of 1 picture" },
              { destination: "On-call webhook", type: "webhook", ok: false, detail: "webhook send ERROR. 502" },
            ],
          }),
        ]}
        fires24h={1}
      />
    );

    const deliveries = wrapper.find('span[data-test="AlertHistoryDelivery"]');
    expect(deliveries).toHaveLength(2);
    expect(deliveries.at(0).hasClass("is-sent")).toBe(true);
    expect(deliveries.at(0).text()).toContain("Slack #ops");
    // A failure says why, on the page, not only on hover.
    expect(deliveries.at(1).hasClass("is-failed")).toBe(true);
    expect(deliveries.at(1).text()).toContain("webhook send ERROR. 502");
  });

  it("says when there was nobody to send it to", () => {
    const wrapper = mount(<AlertHistory history={[fire({ deliveries: [] })]} fires24h={1} />);

    expect(wrapper.find('[data-test="AlertHistoryNobody"]').text()).toContain("no destinations");
  });

  it("says nothing more for an event from before outcomes were kept", () => {
    const wrapper = mount(<AlertHistory history={[fire({ deliveries: null })]} fires24h={1} />);

    expect(wrapper.find('span[data-test="AlertHistoryDelivery"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="AlertHistoryNobody"]').exists()).toBe(false);
  });

  it("says how many it is showing", () => {
    const wrapper = mount(<AlertHistory history={[fire(), fire()]} fires24h={2} />);

    expect(wrapper.find(".alert-history-scope").text()).toBe("the last 2 changes");
  });
});
