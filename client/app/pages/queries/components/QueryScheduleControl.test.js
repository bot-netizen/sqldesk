import React from "react";
import { mount } from "enzyme";
import Dropdown from "antd/lib/dropdown";
import { scheduleForInterval } from "@/components/queries/ScheduleDialog";
import QueryScheduleControl from "./QueryScheduleControl";

const REFRESH_OPTIONS = [60, 300, 3600, 86400, 604800]; // 1m, 5m, 1h, 1d, 1w

function getWrapper({ schedule = null, ...props } = {}) {
  const query = { schedule, isNew: () => false };
  return mount(
    <QueryScheduleControl
      query={query}
      refreshOptions={REFRESH_OPTIONS}
      onSelectInterval={() => {}}
      onEditSchedule={() => {}}
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

function clickItem(menu, label) {
  const item = items(menu).filterWhere((li) => li.text().trim() === label);
  expect(item).toHaveLength(1);
  item.simulate("click");
}

describe("QueryScheduleControl", () => {
  it("offers every allowed interval, plus never and a way to the dialog", () => {
    const labels = items(getMenu(getWrapper())).map((li) => li.text().trim());

    expect(labels).toContain("Never");
    expect(labels).toContain("Every minute");
    expect(labels).toContain("Every 5 minutes");
    expect(labels).toContain("Every hour");
    expect(labels).toContain("At a set time…");
    // one per option, plus Never and the dialog item
    expect(labels).toHaveLength(REFRESH_OPTIONS.length + 2);
  });

  it("reports the chosen interval in seconds", () => {
    const onSelectInterval = jest.fn();
    clickItem(getMenu(getWrapper({ onSelectInterval })), "Every 5 minutes");

    expect(onSelectInterval).toHaveBeenCalledWith(300);
  });

  it("reports never as null rather than as a zero interval", () => {
    // The dialog closes with null for never, and null is what clears a
    // schedule; an interval of 0 would be saved as a schedule.
    const onSelectInterval = jest.fn();
    clickItem(getMenu(getWrapper({ schedule: { interval: 300 }, onSelectInterval })), "Never");

    expect(onSelectInterval).toHaveBeenCalledWith(null);
  });

  it("sends anything needing a time of day to the dialog", () => {
    const onEditSchedule = jest.fn();
    const onSelectInterval = jest.fn();
    clickItem(getMenu(getWrapper({ onEditSchedule, onSelectInterval })), "At a set time\u2026");

    expect(onEditSchedule).toHaveBeenCalled();
    expect(onSelectInterval).not.toHaveBeenCalled();
  });

  it("does not open the menu when scheduling is not allowed", () => {
    expect(getWrapper({ disabled: true }).find(Dropdown).prop("disabled")).toBe(true);
  });
});

describe("scheduleForInterval", () => {
  // Shared with ScheduleDialog so the menu and the dialog cannot produce
  // different schedules for the same interval.
  it("pins a daily schedule to a time of day", () => {
    const daily = scheduleForInterval(null, 86400);

    expect(daily.interval).toBe(86400);
    expect(daily.time).toEqual(expect.stringMatching(/^\d{2}:\d{2}$/));
    expect(daily.day_of_week).toBeNull();
  });

  it("pins a weekly schedule to a weekday as well", () => {
    const weekly = scheduleForInterval(null, 604800);

    expect(weekly.interval).toBe(604800);
    expect(weekly.time).toEqual(expect.stringMatching(/^\d{2}:\d{2}$/));
    expect(weekly.day_of_week).toBeTruthy();
  });

  it("clears the time and weekday when dropping below a day", () => {
    // Otherwise a schedule that used to be weekly keeps a weekday nothing
    // honours, and it reads as "every 5 minutes on Monday".
    const wasWeekly = scheduleForInterval(null, 604800);
    const nowFiveMinutes = scheduleForInterval(wasWeekly, 300);

    expect(nowFiveMinutes.interval).toBe(300);
    expect(nowFiveMinutes.time).toBeNull();
    expect(nowFiveMinutes.day_of_week).toBeNull();
  });

  it("keeps a time somebody already chose", () => {
    const chosen = scheduleForInterval({ interval: 86400, time: "09:30", day_of_week: null, until: null }, 172800);

    expect(chosen.time).toBe("09:30");
  });
});
