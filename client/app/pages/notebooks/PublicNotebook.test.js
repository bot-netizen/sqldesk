import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import PublicNotebookPage from "./PublicNotebook";

jest.mock("@/services/axios", () => ({ axios: { get: jest.fn() } }));
jest.mock("./NotebookCell", () => (props) => <div data-test="cell" data-canedit={String(props.canEdit)} />);
jest.mock("@/components/queries/editor-components", () => ({ getEditorComponents: () => ({ QueryEditor: () => null }) }));

const { axios } = require("@/services/axios");

async function open(answer) {
  axios.get.mockResolvedValueOnce(answer);
  let page;
  await act(async () => {
    page = mount(<PublicNotebookPage token="abc" />);
  });
  page.update();
  return page;
}

/*
  A shared notebook as a reader sees it.

  Read-only by construction rather than by hiding buttons: every cell is
  handed `canEdit={false}`, so none of them offers Run, a chart editor or a
  data source picker -- and there is nothing behind those to call, because
  the public endpoint serves stored slices and nothing else.
*/
describe("a shared notebook", () => {
  beforeEach(() => jest.clearAllMocks());

  it("reads it through the public endpoint, by token", async () => {
    await open({ id: 1, name: "Quarter", cells: [] });

    expect(axios.get).toHaveBeenCalledWith("api/notebooks/public/abc");
  });

  it("shows the notebook's name", async () => {
    const page = await open({ id: 1, name: "Quarter", cells: [] });

    expect(page.find('[data-test="NotebookName"]').text()).toBe("Quarter");
  });

  it("gives every cell to the reader as read-only", async () => {
    const page = await open({
      id: 1,
      name: "Quarter",
      cells: [
        { id: 1, name: "orders", kind: "sql", position: 0, options: {} },
        { id: 2, name: "code_1", kind: "python", position: 1, options: {} },
      ],
    });

    const cells = page.find('[data-test="cell"]');
    expect(cells).toHaveLength(2);
    cells.forEach((one) => expect(one.prop("data-canedit")).toBe("false"));
  });

  it("says so when the link is dead rather than spinning", async () => {
    axios.get.mockRejectedValueOnce(new Error("gone"));
    let page;
    await act(async () => {
      page = mount(<PublicNotebookPage token="abc" />);
    });
    page.update();

    expect(page.text()).toContain("no longer works");
  });
});
