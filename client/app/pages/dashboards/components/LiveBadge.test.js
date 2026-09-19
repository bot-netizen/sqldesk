import React from "react";
import { mount } from "enzyme";
import LiveBadge from "./LiveBadge";

describe("LiveBadge", () => {
  test("nothing for an ordinary dashboard", () => {
    expect(mount(<LiveBadge live={null} />).html()).toBeNull();
  });

  test("live, with how often", () => {
    const text = mount(<LiveBadge live={{ interval: 120, paused: false }} />).text();
    expect(text).toContain("Live");
    expect(text).toContain("every 2 minutes");
  });

  test("paused, and by whom", () => {
    const wrapper = mount(
      <LiveBadge
        live={{ interval: 30, paused: true, paused_by: { name: "Iqbal" }, paused_at: "2026-09-18T10:00:00" }}
      />
    );
    expect(wrapper.text()).toContain("Paused");
    expect(wrapper.text()).toContain("by Iqbal");
    expect(wrapper.find(".live-badge-paused")).toHaveLength(1);
  });
});
