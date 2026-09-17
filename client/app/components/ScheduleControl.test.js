import React from "react";
import { mount } from "enzyme";
import Dropdown from "antd/lib/dropdown";
import ScheduleControl from "./ScheduleControl";

// What a stock installation allows: a minute to a month, twenty-one entries.
const ALL_INTERVALS = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 86400, 604800, 2592000];

function getWrapper({ schedule = null, ...props } = {}) {
  return mount(
    <ScheduleControl
      schedule={schedule}
      isNew={false}
      refreshOptions={ALL_INTERVALS}
      onSelectInterval={() => {}}
      {...props}
    />
  );
}

// The menu lives in the Dropdown's overlay, which antd only mounts once the
// button is clicked. Rendering the overlay element directly tests what the menu
// does without driving the popup open.
function getMenu(wrapper) {
  return mount(wrapper.find(Dropdown).prop("overlay"));
}

// antd 4 renders menu items as bare <li class="ant-menu-item"> with the key
// nowhere in the markup, and renders dividers as <li> too -- so items are
// matched on their label and dividers excluded by class.
function items(menu) {
  return menu.find("li.ant-menu-item");
}

function labels(menu) {
  return items(menu).map((li) => li.text().trim());
}

function clickItem(menu, label) {
  const item = items(menu).filterWhere((li) => li.text().trim() === label);
  expect(item).toHaveLength(1);
  item.simulate("click");
}

describe("ScheduleControl", () => {
  it("offers the intervals people reach for, and nothing else", () => {
    expect(labels(getMenu(getWrapper()))).toEqual([
      "Never",
      "Every 5 minutes",
      "Every 10 minutes",
      "Every 15 minutes",
      "Every 30 minutes",
      "Every hour",
      "Every 3 hours",
      "Every 6 hours",
      "Every day",
    ]);
  });

  it("leaves out an interval this installation does not allow", () => {
    // An org can narrow the list; offering something that would be refused is
    // worse than a shorter menu.
    const menu = getMenu(getWrapper({ refreshOptions: [1800, 3600] }));

    expect(labels(menu)).toEqual(["Never", "Every 30 minutes", "Every hour"]);
  });

  it("reports the chosen interval in seconds", () => {
    const onSelectInterval = jest.fn();
    clickItem(getMenu(getWrapper({ onSelectInterval })), "Every 15 minutes");

    expect(onSelectInterval).toHaveBeenCalledWith(900);
  });

  it("reports never as null rather than as a zero interval", () => {
    // null is what clears a schedule; an interval of 0 would be stored as one.
    const onSelectInterval = jest.fn();
    clickItem(getMenu(getWrapper({ schedule: { interval: 300 }, onSelectInterval })), "Never");

    expect(onSelectInterval).toHaveBeenCalledWith(null);
  });

  it("reads back a crontab schedule set before the menu dropped them", () => {
    // The expression is no longer offered, but a query that already carries one
    // still runs on it, so the button has to say so rather than read "Never".
    const wrapper = getWrapper({ schedule: { interval: null, cron: "0 9 * * 1-5" } });

    expect(wrapper.text()).toContain("0 9 * * 1-5");
    expect(labels(getMenu(wrapper))).not.toContain("Custom…");
  });

  it("marks the interval currently in force", () => {
    const menu = getMenu(getWrapper({ schedule: { interval: 1800 } }));

    expect(menu.find(Dropdown).length).toBe(0); // sanity: we have the menu, not the button
    expect(menu.find("li.ant-menu-item-selected").text().trim()).toBe("Every 30 minutes");
  });

  it("shows the expression on the button", () => {
    const wrapper = getWrapper({ schedule: { interval: null, cron: "0 9 * * 1-5" } });

    expect(wrapper.text()).toContain("0 9 * * 1-5");
  });

  it("does not open the menu when scheduling is not allowed", () => {
    expect(getWrapper({ disabled: true }).find(Dropdown).prop("disabled")).toBe(true);
  });
});
