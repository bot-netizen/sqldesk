import React from "react";
import { mount } from "enzyme";

import ScreenshotFrame, { generatedAt } from "./ScreenshotFrame";

/*
  The branded page the renderer photographs: the same band Export as image
  draws, so a picture sent to Slack and one exported by hand match.
*/

describe("ScreenshotFrame", () => {
  it("carries the mark, the name and the provenance", () => {
    const wrapper = mount(
      <ScreenshotFrame
        title="Revenue this quarter"
        fields={[{ label: "Generated at", value: "13 Nov 2026, 01:44 UTC" }]}
      >
        <div className="grid">the dashboard</div>
      </ScreenshotFrame>
    );

    expect(wrapper.find(".screenshot-frame__brand").text()).toBe("SQLDesk");
    expect(wrapper.find(".screenshot-frame__title").text()).toBe("Revenue this quarter");
    expect(wrapper.find(".screenshot-frame__fields").text()).toBe("Generated at: 13 Nov 2026, 01:44 UTC");
    expect(wrapper.find(".grid").text()).toBe("the dashboard");
  });

  it("is what the renderer looks for, so the picture is cropped to it", () => {
    // screenshots/service.py: FRAME_SELECTOR
    const wrapper = mount(<ScreenshotFrame title="x" />);

    expect(wrapper.find('[data-test="ScreenshotFrame"]').exists()).toBe(true);
  });

  it("leaves out a field with nothing in it", () => {
    const wrapper = mount(<ScreenshotFrame title="x" fields={[{ label: "Owner", value: "" }]} />);

    expect(wrapper.find(".screenshot-frame__fields").exists()).toBe(false);
  });

  it("names the time zone, because a channel spans them", () => {
    expect(generatedAt(new Date("2026-11-13T01:44:00Z"))).toMatch(/13 Nov 2026, 03:44 [A-Z+0-9:]+/);
  });
});
