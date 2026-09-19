import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import { resetServerClock, syncServerClock } from "@/lib/serverClock";
import LiveCountdown, { formatRemaining } from "./LiveCountdown";

function secondsAgo(seconds) {
  return new Date(Date.now() - seconds * 1000).toISOString();
}

describe("LiveCountdown", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    jest.useRealTimers();
    resetServerClock();
  });

  test("counts down to the next refresh, and only that", () => {
    const wrapper = mount(<LiveCountdown updatedAt={secondsAgo(12)} interval={30} />);
    expect(wrapper.text()).toBe("next in 18s");

    act(() => {
      jest.advanceTimersByTime(5000);
    });
    expect(wrapper.text()).toBe("next in 13s");
  });

  test("says it is refreshing once the time is up", () => {
    const wrapper = mount(<LiveCountdown updatedAt={secondsAgo(45)} interval={30} />);
    expect(wrapper.text()).toBe("refreshing…");
  });

  test("paused, says how old the result is instead", () => {
    const wrapper = mount(<LiveCountdown updatedAt={secondsAgo(120)} interval={null} />);
    expect(wrapper.text()).toMatch(/^updated /);
    expect(wrapper.text()).not.toMatch(/next in/);
  });

  test("counts on the server's clock, not the browser's", () => {
    // The browser is ten seconds slow: the server's 12-second-old result is 22.
    syncServerClock(new Date(Date.now() + 10000).toISOString());
    const wrapper = mount(
      <LiveCountdown updatedAt={new Date(Date.now() + 10000 - 12000).toISOString()} interval={30} />
    );
    expect(wrapper.text()).toBe("next in 18s");
    const wrong = mount(<LiveCountdown updatedAt={secondsAgo(12)} interval={30} />);
    expect(wrong.text()).toBe("next in 8s");
  });

  test("minutes for the longer intervals", () => {
    expect(formatRemaining(45)).toBe("45s");
    expect(formatRemaining(60)).toBe("1m");
    expect(formatRemaining(125)).toBe("2m 5s");
  });
});
