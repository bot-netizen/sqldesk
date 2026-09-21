import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import moment from "moment";
import Timer from "./Timer";

/*
  A Timer with nothing to count from is the common case, not an edge one.

  Every dashboard widget renders the refresh indicator all the time -- CSS
  hides it until that widget is actually refreshing -- so on a dashboard of 25
  widgets there are 25 Timers with `from` null. Each one used to subtract from
  NaN once a second and write "Invalid date" into a hidden span, for as long as
  the page was open. Found on the wall display, which is a page that is never
  closed.
*/

describe("Timer", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  test("counts up from the time it is given", () => {
    const wrapper = mount(<Timer from={moment().subtract(65, "seconds")} />);
    expect(wrapper.find("span.rd-timer").text()).toBe("01:05");
  });

  test("switches to hours once there are hours to show", () => {
    const wrapper = mount(<Timer from={moment().subtract(2, "hours")} />);
    expect(wrapper.find("span.rd-timer").text()).toBe("02:00:00");
  });

  test("shows nothing when there is nothing to count from", () => {
    // Not "Invalid date", which is what NaN formats to and what every idle
    // widget on a dashboard used to hold.
    const wrapper = mount(<Timer />);
    expect(wrapper.find("span.rd-timer").text()).toBe("");
  });

  test("shows nothing when what it is given is not a time", () => {
    const wrapper = mount(<Timer from="soon" />);
    expect(wrapper.find("span.rd-timer").text()).toBe("");
  });

  test("does no work at all with nothing to count from", () => {
    // The point of the fix: no interval, so an idle widget costs nothing.
    const before = jest.getTimerCount();
    mount(<Timer />);
    expect(jest.getTimerCount()).toBe(before);
  });

  test("ticks while it has something to count", () => {
    const before = jest.getTimerCount();
    const wrapper = mount(<Timer from={moment()} />);
    expect(jest.getTimerCount()).toBe(before + 1);

    act(() => {
      jest.advanceTimersByTime(3000);
    });
    wrapper.update();
    expect(wrapper.find("span.rd-timer").text()).toBe("00:03");
  });

  test("stops ticking when it is taken away", () => {
    // A widget finishes refreshing by having its start time set back to null.
    const before = jest.getTimerCount();
    const wrapper = mount(<Timer from={moment()} />);
    expect(jest.getTimerCount()).toBe(before + 1);

    wrapper.setProps({ from: null });
    expect(jest.getTimerCount()).toBe(before);
    expect(wrapper.find("span.rd-timer").text()).toBe("");
  });
});
