import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import organizationStatus from "@/services/organizationStatus";
import EmptyState from "./EmptyState";

jest.mock("@/services/auth", () => ({ currentUser: { isAdmin: true } }));
jest.mock("@/components/dashboards/CreateDashboardDialog", () => ({ showModal: jest.fn() }));
jest.mock("@/services/organizationStatus", () => ({
  // What the app fetched when it opened: nothing done yet.
  objectCounters: { data_sources: 0, queries: 0, alerts: 0, dashboards: 0, users: 1 },
  refresh: jest.fn(),
}));

function doneSteps(wrapper) {
  return wrapper.find("li.done").map((li) => li.text());
}

describe("EmptyState", () => {
  test("ticks off what was done since the app opened, without a reload", async () => {
    organizationStatus.refresh.mockResolvedValue({
      objectCounters: { data_sources: 1, queries: 0, alerts: 0, dashboards: 1, users: 1 },
    });
    const wrapper = mount(
      <EmptyState description="Nothing here" illustration="dashboard" showDashboardStep showDataSourceStep />
    );
    expect(doneSteps(wrapper)).toEqual([]);

    await act(async () => {
      await Promise.resolve();
    });
    wrapper.update();

    expect(organizationStatus.refresh).toHaveBeenCalled();
    expect(doneSteps(wrapper)).toEqual(
      expect.arrayContaining([expect.stringContaining("Data Source"), expect.stringContaining("Dashboard")])
    );
    expect(doneSteps(wrapper)).toHaveLength(2);
  });
});
