import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";

import { DashboardEditControl } from "./DashboardHeader";
import { DashboardStatusEnum } from "../hooks/useEditModeHandler";

/*
  The controls that decide whether a dashboard's layout is kept or thrown
  away. Worth testing directly: the layout now lives only in the browser until
  one of these buttons is pressed, so a mis-wired one loses work rather than
  merely looking wrong.
*/

jest.mock("antd/lib/modal", () => ({
  __esModule: true,
  default: { confirm: jest.fn() },
}));

// eslint-disable-next-line import/first
import Modal from "antd/lib/modal";

function config(overrides = {}) {
  return {
    dashboard: { dashboard_filters_enabled: false },
    updateDashboard: jest.fn(),
    setEditingLayout: jest.fn(),
    dashboardStatus: DashboardStatusEnum.SAVED,
    hasUnsavedChanges: false,
    saveDashboardLayout: jest.fn(() => Promise.resolve(true)),
    discardDashboardLayout: jest.fn(),
    saveDashboardParameters: jest.fn(() => Promise.resolve()),
    ...overrides,
  };
}

function render(overrides) {
  const dashboardConfiguration = config(overrides);
  const wrapper = mount(<DashboardEditControl dashboardConfiguration={dashboardConfiguration} />);
  return { wrapper, dashboardConfiguration };
}

const button = (wrapper, testId) => wrapper.find(`button[data-test="${testId}"]`);

async function click(wrapper, testId) {
  await act(async () => {
    button(wrapper, testId).simulate("click");
  });
  wrapper.update();
}

describe("the dashboard editing controls", () => {
  beforeEach(() => Modal.confirm.mockClear());

  test("offer both keeping and throwing away", () => {
    const { wrapper } = render();
    expect(button(wrapper, "DashboardDoneEditingButton").text()).toContain("Done Editing");
    expect(button(wrapper, "DashboardDiscardButton").text()).toContain("Discard");
  });

  describe("the status beside them", () => {
    test.each([
      [DashboardStatusEnum.SAVED, "No changes"],
      [DashboardStatusEnum.UNSAVED, "Unsaved changes"],
      [DashboardStatusEnum.SAVING, "Saving"],
      [DashboardStatusEnum.SAVING_FAILED, "Saving Failed"],
    ])("says %s as %s", (dashboardStatus, text) => {
      const { wrapper } = render({ dashboardStatus });
      expect(wrapper.find(".save-status").text()).toBe(text);
    });

    test("marks unsaved changes for the stylesheet to colour", () => {
      const { wrapper } = render({ dashboardStatus: DashboardStatusEnum.UNSAVED });
      expect(wrapper.find(".save-status").prop("data-unsaved")).toBe(true);
    });
  });

  describe("Done Editing", () => {
    test("saves the parameters and the layout, then leaves edit mode", async () => {
      const { wrapper, dashboardConfiguration } = render({ hasUnsavedChanges: true });
      await click(wrapper, "DashboardDoneEditingButton");

      expect(dashboardConfiguration.saveDashboardParameters).toHaveBeenCalled();
      expect(dashboardConfiguration.saveDashboardLayout).toHaveBeenCalled();
      expect(dashboardConfiguration.setEditingLayout).toHaveBeenCalledWith(false);
    });

    test("stays in edit mode when the save fails", async () => {
      // The arrangement exists nowhere but this browser, so leaving now would
      // be the one thing that loses it.
      const { wrapper, dashboardConfiguration } = render({
        hasUnsavedChanges: true,
        saveDashboardLayout: jest.fn(() => Promise.resolve(false)),
      });
      await click(wrapper, "DashboardDoneEditingButton");

      expect(dashboardConfiguration.setEditingLayout).not.toHaveBeenCalled();
    });

    test("offers to try again after a failure", () => {
      const { wrapper } = render({ dashboardStatus: DashboardStatusEnum.SAVING_FAILED });
      expect(button(wrapper, "DashboardDoneEditingButton").text()).toContain("Retry");
    });
  });

  describe("Discard", () => {
    test("asks first when there is something to lose", async () => {
      const { wrapper, dashboardConfiguration } = render({ hasUnsavedChanges: true });
      await click(wrapper, "DashboardDiscardButton");

      expect(Modal.confirm).toHaveBeenCalled();
      // Nothing thrown away until the question is answered.
      expect(dashboardConfiguration.discardDashboardLayout).not.toHaveBeenCalled();
      expect(dashboardConfiguration.setEditingLayout).not.toHaveBeenCalled();
    });

    test("throws the changes away once that is confirmed", async () => {
      const { wrapper, dashboardConfiguration } = render({ hasUnsavedChanges: true });
      await click(wrapper, "DashboardDiscardButton");

      await act(async () => {
        Modal.confirm.mock.calls[0][0].onOk();
      });

      expect(dashboardConfiguration.discardDashboardLayout).toHaveBeenCalled();
      expect(dashboardConfiguration.setEditingLayout).toHaveBeenCalledWith(false);
    });

    test("just leaves when there is nothing to lose", async () => {
      const { wrapper, dashboardConfiguration } = render({ hasUnsavedChanges: false });
      await click(wrapper, "DashboardDiscardButton");

      expect(Modal.confirm).not.toHaveBeenCalled();
      expect(dashboardConfiguration.setEditingLayout).toHaveBeenCalledWith(false);
    });

    test("never saves", async () => {
      const { wrapper, dashboardConfiguration } = render({ hasUnsavedChanges: true });
      await click(wrapper, "DashboardDiscardButton");
      await act(async () => {
        Modal.confirm.mock.calls[0][0].onOk();
      });

      expect(dashboardConfiguration.saveDashboardLayout).not.toHaveBeenCalled();
    });
  });
});
