const mockGet = jest.fn();

jest.mock("@/services/axios", () => ({
  axios: {
    get: (...args) => mockGet(...args),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

// eslint-disable-next-line import/first
import React from "react";
// eslint-disable-next-line import/first
import { act } from "react-dom/test-utils";
// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import SlackChannelSelect, { inviteCommand } from "./SlackChannelSelect";

/*
  The channel list is the app's own channels, and says how to add another.

  A list that does not have #ops is met with "where is #ops?", so the answer --
  the /invite command, with the app's real name in it -- is said under the list
  every time, and is the whole message when the app is in no channel at all.
*/

async function render(props = {}) {
  let wrapper;
  await act(async () => {
    wrapper = mount(<SlackChannelSelect onChange={() => {}} {...props} />);
  });
  wrapper.update();
  return wrapper;
}

function options(wrapper) {
  return wrapper.find("Select").first().prop("options");
}

describe("SlackChannelSelect", () => {
  afterEach(() => mockGet.mockReset());

  it("offers the channels the server says the app is in", async () => {
    mockGet.mockResolvedValue({
      channels: [
        { id: "C1", name: "general", private: false },
        { id: "C2", name: "secrets", private: true },
      ],
      app_name: "sqldesk",
    });

    const wrapper = await render();

    expect(mockGet).toHaveBeenCalledWith("api/slack/channels");
    expect(options(wrapper)).toEqual([
      { value: "C1", label: "#general" },
      { value: "C2", label: "#secrets (private)" },
    ]);
  });

  it("says how to add a channel, with the app's own name", async () => {
    mockGet.mockResolvedValue({ channels: [{ id: "C1", name: "general" }], app_name: "sqldesk" });

    const wrapper = await render();

    const hint = wrapper.find('[data-test="SlackChannelHint"]').text();
    expect(hint).toContain("Only channels the app has been added to are listed");
    expect(hint).toContain("/invite @sqldesk");
  });

  it("with no channel at all, says that is the problem and how to fix it", async () => {
    mockGet.mockResolvedValue({ channels: [], app_name: "sqldesk" });

    const wrapper = await render();

    expect(wrapper.find("Select").first().prop("disabled")).toBe(true);
    expect(wrapper.find('[data-test="SlackChannelHint"]').text()).toContain(
      "The app has not been added to any channel"
    );
  });

  it("shows Slack's own reason when the list cannot be read", async () => {
    mockGet.mockRejectedValue({ response: { data: { message: "That token has been revoked in Slack." } } });

    const wrapper = await render();

    expect(wrapper.find("Alert").first().prop("message")).toBe("That token has been revoked in Slack.");
    expect(wrapper.find('[data-test="SlackChannelHint"]').exists()).toBe(false);
  });

  it("hands back the channel with its id, so a caller can name it", async () => {
    mockGet.mockResolvedValue({ channels: [{ id: "C1", name: "general" }], app_name: "sqldesk" });
    const onChange = jest.fn();

    const wrapper = await render({ onChange });
    act(() => {
      wrapper.find("Select").first().prop("onChange")("C1");
    });

    expect(onChange).toHaveBeenCalledWith("C1", { id: "C1", name: "general" });
  });

  it("falls back to words when the app's name is not known", () => {
    expect(inviteCommand(null)).toBe("/invite and the app's name");
  });
});
