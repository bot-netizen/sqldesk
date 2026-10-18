import React from "react";
import { mount } from "enzyme";

import { VerifiedBadge } from "./DashboardHeader";

/*
  The verified badge beside a dashboard's title.

  The note is the point, so it opens on click -- a phone has no hover -- and a
  dashboard that has changed since it was checked says so, rather than
  vouching for charts nobody verified.
*/
const CHECKED = {
  by: "Iqbal",
  at: "2026-10-18T12:00:00Z",
  note: "Revenue ties out to finance's monthly close.",
  changed_since: false,
};

describe("the verified badge", () => {
  test("nothing at all when nobody has verified it", () => {
    const wrapper = mount(<VerifiedBadge verification={null} />);

    expect(wrapper.find('[data-test="VerifiedBadge"]').exists()).toBe(false);
  });

  test("says verified, and on a tap who checked it and what they checked", () => {
    const wrapper = mount(<VerifiedBadge verification={CHECKED} />);

    expect(wrapper.find('button[data-test="VerifiedBadge"]').text()).toContain("verified");
    wrapper.find('button[data-test="VerifiedBadge"]').simulate("click");

    const note = wrapper.find('[data-test="VerificationNote"]').first().text();
    expect(note).toContain("Iqbal");
    expect(note).toContain("Revenue ties out");
    expect(wrapper.find('[data-test="VerificationChanged"]').exists()).toBe(false);
  });

  test("a dashboard that changed since does not pretend otherwise", () => {
    const wrapper = mount(<VerifiedBadge verification={{ ...CHECKED, changed_since: true }} />);

    expect(wrapper.find('button[data-test="VerifiedBadge"]').text()).toContain("verified, then changed");
    wrapper.find('button[data-test="VerifiedBadge"]').simulate("click");
    expect(wrapper.find('[data-test="VerificationChanged"]').exists()).toBe(true);
  });
});
