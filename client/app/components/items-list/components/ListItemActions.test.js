import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import ListItemActions, { canManagePermissions } from "./ListItemActions";
import { currentUser } from "@/services/auth";

jest.mock("@/services/notification", () => ({ success: jest.fn(), error: jest.fn() }));
jest.mock("@/components/PermissionsEditorDialog", () => ({ showModal: jest.fn() }));
jest.mock("antd/lib/modal", () => ({ confirm: jest.fn(({ onOk }) => onOk && onOk()) }));

const notification = require("@/services/notification");

describe("canManagePermissions", () => {
  afterEach(() => {
    currentUser.permissions = [];
    currentUser.isAdmin = false;
  });

  test("admins can manage permissions", () => {
    currentUser.permissions = ["admin"];
    expect(canManagePermissions()).toBe(true);
  });

  test("non-admins cannot, even when they own the object", () => {
    // Deliberately narrower than the API, which uses require_admin_or_owner.
    // If this ever relaxes to owner-or-admin, that is a decision to make on
    // purpose, not to drift into.
    currentUser.permissions = ["create_query", "list_dashboards"];
    expect(canManagePermissions()).toBe(false);
  });

  test("returns a boolean, not a truthy permissions array", () => {
    currentUser.permissions = ["admin"];
    expect(typeof canManagePermissions()).toBe("boolean");
  });
});

/*
  The row menu, and the two destructive actions in it.

  Archiving a query already throws away its alerts and its dashboard widgets,
  so "archived" sounds reversible and is not -- and people archive things to
  get rid of them and then find the archive full. Deleting outright is a
  separate entry rather than a flag on the first, because one of them cannot
  be undone.
*/
/**
 * The menu itself.
 *
 * Mounted from the Dropdown's `overlay` rather than by finding it in the
 * rendered tree: antd does not render an overlay until the dropdown is
 * opened, so a `.find("Menu")` on the trigger finds nothing and every
 * assertion about the entries passes or fails for the wrong reason.
 */
function menu(props = {}) {
  const trigger = mount(<ListItemActions item={{ id: 1, name: "Quarterly rollup" }} {...props} />);
  const dropdown = trigger.find("Dropdown");
  if (!dropdown.exists()) {
    return trigger;
  }
  return mount(dropdown.prop("overlay"));
}

describe("the entries offered", () => {
  beforeEach(() => jest.clearAllMocks());

  it("offers nothing at all when there is nothing to offer", () => {
    expect(mount(<ListItemActions item={{ id: 1, name: "x" }} />).isEmptyRender()).toBe(true);
  });

  it("offers archiving on its own, as it always has", () => {
    const entries = menu({ onDelete: jest.fn() });

    expect(entries.find('[data-test="ListItemDelete"]').exists()).toBe(true);
    expect(entries.find('[data-test="ListItemPermanentDelete"]').exists()).toBe(false);
  });

  it("offers deleting outright only when something can do it", () => {
    const entries = menu({ onDelete: jest.fn(), onPermanentDelete: jest.fn() });

    expect(entries.find('[data-test="ListItemPermanentDelete"]').exists()).toBe(true);
  });

  it("offers deleting without archiving, for a list that has no archive", () => {
    const entries = menu({ onPermanentDelete: jest.fn() });

    expect(entries.find('[data-test="ListItemPermanentDelete"]').exists()).toBe(true);
    expect(entries.find('[data-test="ListItemDelete"]').exists()).toBe(false);
  });
});

describe("deleting outright", () => {
  beforeEach(() => jest.clearAllMocks());

  it("asks first, and the question is its own rather than the archive's", async () => {
    const Modal = require("antd/lib/modal");
    const onPermanentDelete = jest.fn(() => Promise.resolve());
    const entries = menu({
      onDelete: jest.fn(),
      onPermanentDelete,
      permanentDeleteConfirm: {
        title: "Delete query permanently",
        content: "This cannot be undone.",
        okText: "Delete",
      },
    });

    await act(async () => {
      entries.find('[data-test="ListItemPermanentDelete"]').first().simulate("click");
    });

    expect(Modal.confirm).toHaveBeenCalled();
    expect(Modal.confirm.mock.calls[0][0].title).toBe("Delete query permanently");
    expect(onPermanentDelete).toHaveBeenCalledWith({ id: 1, name: "Quarterly rollup" });
  });

  it("says what was deleted, by name", async () => {
    const entries = menu({ onPermanentDelete: jest.fn(() => Promise.resolve()) });

    await act(async () => {
      entries.find('[data-test="ListItemPermanentDelete"]').first().simulate("click");
    });

    expect(notification.success).toHaveBeenCalledWith('Deleted "Quarterly rollup".');
  });

  it("surfaces the API's refusal rather than assuming the click was allowed", async () => {
    const entries = menu({ onPermanentDelete: jest.fn(() => Promise.reject(new Error("not yours"))) });

    await act(async () => {
      entries.find('[data-test="ListItemPermanentDelete"]').first().simulate("click");
    });

    expect(notification.error).toHaveBeenCalled();
    expect(notification.error.mock.calls[0][0]).toBe("Delete failed.");
  });

  it("does nothing at all when the question is answered no", async () => {
    const Modal = require("antd/lib/modal");
    Modal.confirm.mockImplementationOnce(({ onCancel }) => onCancel && onCancel());
    const onPermanentDelete = jest.fn(() => Promise.resolve());
    const entries = menu({ onPermanentDelete });

    await act(async () => {
      entries.find('[data-test="ListItemPermanentDelete"]').first().simulate("click");
    });

    expect(onPermanentDelete).not.toHaveBeenCalled();
  });
});
