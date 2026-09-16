import { currentUser } from "@/services/auth";
import { canManagePermissions } from "./ListItemActions";

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
