jest.mock("@/services/auth", () => ({
  clientConfig: {},
  currentUser: { hasPermission: jest.fn(() => true) },
}));

jest.mock("@/services/axios", () => ({
  axios: {
    get: () => Promise.resolve({}),
    post: () => Promise.resolve({}),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

// eslint-disable-next-line import/first
import React from "react";
// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import { currentUser } from "@/services/auth";
// eslint-disable-next-line import/first
import SendableNotice from "./SendableNotice";

/*
  Too big to send is said as a dialog opens, with what to do about it.
*/

const TOO_BIG = {
  fits: false,
  widgets: 15,
  max_widgets: 12,
  remove: 3,
  problem: "A dashboard is sent as a one-page report: up to 12 widgets, one page tall. This dashboard has 15 widgets.",
  advice: "To send it, remove 3 widgets, or send a copy of it with just the widgets that matter.",
};

describe("SendableNotice", () => {
  const dashboard = { id: 7, name: "Sales" };

  it("says nothing about a dashboard that fits", () => {
    const wrapper = mount(<SendableNotice dashboard={dashboard} check={{ fits: true }} />);

    expect(wrapper.html()).toBeNull();
  });

  it("nor before the answer has arrived", () => {
    const wrapper = mount(<SendableNotice dashboard={dashboard} check={null} />);

    expect(wrapper.html()).toBeNull();
  });

  it("says why it cannot be sent and what to change", () => {
    const wrapper = mount(<SendableNotice dashboard={dashboard} check={TOO_BIG} />);

    const text = wrapper.text();
    expect(text).toContain("This dashboard has 15 widgets");
    expect(text).toContain("remove 3 widgets");
  });

  it("offers a copy to trim to somebody who may make one", () => {
    currentUser.hasPermission.mockReturnValue(true);

    const wrapper = mount(<SendableNotice dashboard={dashboard} check={TOO_BIG} />);

    expect(wrapper.text()).toContain("Make a copy to trim");
    expect(currentUser.hasPermission).toHaveBeenCalledWith("edit_dashboard");
  });

  it("and not to somebody who may not", () => {
    currentUser.hasPermission.mockReturnValue(false);

    const wrapper = mount(<SendableNotice dashboard={dashboard} check={TOO_BIG} />);

    expect(wrapper.text()).not.toContain("Make a copy to trim");
  });
});
