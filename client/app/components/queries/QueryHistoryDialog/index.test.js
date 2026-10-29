import React from "react";
import { mount } from "enzyme";
import Modal from "antd/lib/modal";

import { Unwrapped as QueryHistoryDialog } from "./index";
import { axios } from "@/services/axios";

/*
  What the History dialog shows, and what pressing Restore does.

  The behaviour worth pinning is the pair of comparisons. "What changed here"
  and "against the query now" are different questions — the second is the one
  somebody about to restore actually has — and a dialog that answered one while
  labelling it the other would be worse than offering only one.
*/
function version(number, overrides) {
  return {
    id: 100 + number,
    number,
    at: "2026-10-01T12:00:00Z",
    by: { id: 1, name: "Iqbal", email: "iqbal@example.com" },
    changed: ["SQL"],
    values: { name: "Orders", description: "", query: `select ${number}`, tags: [], schedule: null, options: {} },
    ...overrides,
  };
}

function query(overrides) {
  return {
    id: 7,
    name: "Orders",
    description: "",
    query: "select 3",
    tags: [],
    schedule: null,
    options: {},
    clone() {
      return { ...this };
    },
    ...overrides,
  };
}

const dialog = () => ({ props: { visible: true }, close: jest.fn(), dismiss: jest.fn() });

async function render(versions, props) {
  jest.spyOn(axios, "get").mockResolvedValue({ versions });
  const shown = mount(<QueryHistoryDialog dialog={dialog()} query={query()} {...props} />);
  await Promise.resolve();
  shown.update();
  return shown;
}

describe("the History dialog", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("lists the versions newest first, numbered and attributed", async () => {
    const shown = await render([version(3), version(2), version(1)]);
    const text = shown.find('[data-test="QueryHistoryList"]').text();

    expect(text.indexOf("#3")).toBeLessThan(text.indexOf("#1"));
    expect(text).toContain("Iqbal");
  });

  test("it opens on the newest version and diffs it against the one before", async () => {
    const shown = await render([version(3), version(2)]);
    const diff = shown.find('[data-test="QueryHistoryDiff"]').text();

    expect(diff).toContain("select 2");
    expect(diff).toContain("select 3");
  });

  test("choosing an older version diffs that one instead", async () => {
    const shown = await render([version(3), version(2), version(1)]);

    shown.find(".query-history-entry").at(2).simulate("click");

    // Version 1 is the oldest shown, so there is nothing older to compare it
    // with — it reads as the whole query being added.
    expect(shown.find('[data-test="QueryHistoryDiff"]').text()).toContain("select 1");
  });

  test("against the query now, it compares with what is on screen", async () => {
    // The query is at "select 3" and the version holds "select 2", so this
    // comparison has to show both — and would show neither if the toggle were
    // wired to the previous version again.
    const shown = await render([version(2), version(1)]);

    shown.find('input[value="current"]').simulate("change", { target: { value: "current" } });
    shown.update();
    const diff = shown.find('[data-test="QueryHistoryDiff"]').text();

    expect(diff).toContain("select 3");
    expect(diff).toContain("select 2");
  });

  test("a version whose SQL matches says so rather than showing an empty box", async () => {
    const same = version(2, { values: { ...version(2).values, query: "select 3" } });
    const shown = await render([same, version(1, { values: { ...version(1).values, query: "select 3" } })]);

    expect(shown.text()).toContain("The SQL is the same.");
  });

  test("a change to the name is named, not only shown as a diff of nothing", async () => {
    const renamed = version(2, { changed: ["Name"], values: { ...version(2).values, name: "Orders by day" } });
    const shown = await render([renamed, version(1)]);

    expect(shown.text()).toContain("Orders by day");
  });

  test("Restore is offered only to somebody who could have made the edit", async () => {
    const readOnly = await render([version(2), version(1)], { canRestore: false });
    expect(readOnly.find('[data-test="RestoreVersion"]').length).toBe(0);

    const editor = await render([version(2), version(1)], { canRestore: true });
    expect(editor.find('[data-test="RestoreVersion"]').length).toBeGreaterThan(0);
  });

  test("restoring posts to that version and hands the updated query back", async () => {
    const post = jest.spyOn(axios, "post").mockResolvedValue({ id: 7, query: "select 2" });
    const closing = dialog();
    jest.spyOn(axios, "get").mockResolvedValue({ versions: [version(2), version(1)] });
    const shown = mount(<QueryHistoryDialog dialog={closing} query={query()} canRestore />);
    await Promise.resolve();
    shown.update();

    shown.find('[data-test="RestoreVersion"]').first().simulate("click");
    await Promise.resolve();
    await Promise.resolve();

    expect(post).toHaveBeenCalledWith("api/queries/7/versions/102/restore");
    expect(closing.close).toHaveBeenCalledWith(expect.objectContaining({ query: "select 2" }));
  });

  test("with unsaved changes in the editor, restoring asks first and posts only on yes", async () => {
    const post = jest.spyOn(axios, "post").mockResolvedValue({ id: 7, query: "select 2" });
    const confirm = jest.spyOn(Modal, "confirm").mockImplementation(() => {});
    const shown = await render([version(2), version(1)], { canRestore: true, unsaved: true });

    shown.find('[data-test="RestoreVersion"]').first().simulate("click");

    expect(confirm).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Restore version 2?", okText: "Restore and discard my changes" })
    );
    expect(post).not.toHaveBeenCalled();

    confirm.mock.calls[0][0].onOk();
    expect(post).toHaveBeenCalledWith("api/queries/7/versions/102/restore");
  });

  test("with nothing unsaved, restoring does not ask", async () => {
    jest.spyOn(axios, "post").mockResolvedValue({ id: 7, query: "select 2" });
    const confirm = jest.spyOn(Modal, "confirm").mockImplementation(() => {});
    const shown = await render([version(2), version(1)], { canRestore: true });

    shown.find('[data-test="RestoreVersion"]').first().simulate("click");

    expect(confirm).not.toHaveBeenCalled();
  });

  test("a query with nothing recorded says what records a version", async () => {
    const shown = await render([]);

    expect(shown.text()).toContain("Nothing recorded yet");
  });

  test("and a history that would not load says that instead of nothing", async () => {
    jest.spyOn(axios, "get").mockRejectedValue(new Error("no"));
    const shown = mount(<QueryHistoryDialog dialog={dialog()} query={query()} />);
    await Promise.resolve();
    await Promise.resolve();
    shown.update();

    expect(shown.text()).toContain("Could not load");
  });
});
