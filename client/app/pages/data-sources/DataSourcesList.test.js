import React from "react";
import { mount } from "enzyme";
import { DataSourcesListComponent } from "./DataSourcesList";

jest.mock("@/services/policy", () => ({ policy: { isCreateDataSourceEnabled: () => true } }));
jest.mock("@/services/recordEvent", () => jest.fn());
jest.mock("@/components/CreateSourceDialog", () => ({ showModal: jest.fn() }));

/*
  A paused data source refuses everything -- queries, scheduled refreshes,
  live dashboards, the catalog, AI clients. That is the point of the switch,
  and it is also why it has to be visible: an admin looking at a wall of
  failing dashboards should find out here rather than by opening each source
  in turn.
*/
function sources(extras = []) {
  return [{ id: 1, name: "Warehouse", type: "pg", paused: false }, ...extras];
}

describe("the data sources list", () => {
  it("marks a paused source", () => {
    const list = mount(
      <DataSourcesListComponent
        dataSources={sources([{ id: 2, name: "Replica", type: "pg", paused: true }])}
        onClickCreate={jest.fn()}
      />
    );

    expect(list.find(".visual-card-badge").map((one) => one.text())).toEqual(["Paused"]);
  });

  it("marks nothing when everything is running", () => {
    const list = mount(<DataSourcesListComponent dataSources={sources()} onClickCreate={jest.fn()} />);

    expect(list.find(".visual-card-badge").exists()).toBe(false);
  });
});
