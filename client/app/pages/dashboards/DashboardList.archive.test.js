import { viewsFor, STREAMING_BASE } from "./DashboardList";

jest.mock("@/services/auth", () => ({ currentUser: { name: "Test", profile_image_url: "" } }));
jest.mock("@/services/routes", () => ({ register: jest.fn(), normalizeUrl: (u) => u }));

/*
  Archiving a dashboard hid it everywhere and there was no list of what had
  been hidden: the flag and the Archive action both existed since the fork,
  and the only way back was remembering the address. Queries have had their
  archive all along.
*/
describe("Dashboard list views", () => {
  test("the ordinary half offers Archived", () => {
    const keys = viewsFor("saved").map((v) => v.key);

    expect(keys).toContain("archive");
  });

  test("so does the streaming half, because the views repeat inside each", () => {
    const keys = viewsFor("streaming").map((v) => v.key);

    expect(keys).toContain("archive");
  });

  test("the streaming half's Archived points inside that half", () => {
    const archived = viewsFor("streaming").find((v) => v.key === "archive");

    expect(archived.href).toContain(STREAMING_BASE);
  });

  test("and the ordinary half's does not", () => {
    const archived = viewsFor("saved").find((v) => v.key === "archive");

    expect(archived.href).not.toContain(STREAMING_BASE);
  });

  test("it comes after the views somebody uses daily", () => {
    // An archive is where you go occasionally; All, Mine and Favorites are
    // where you go every day.
    const keys = viewsFor("saved").map((v) => v.key);

    expect(keys.indexOf("archive")).toBe(keys.length - 1);
  });
});
