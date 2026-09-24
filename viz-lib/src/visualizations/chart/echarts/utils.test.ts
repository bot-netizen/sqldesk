import moment from "moment";
import { normalizeX } from "./utils";

/*
  A time axis wants epoch milliseconds. Where those come from matters for
  speed -- a result's timestamp cells are already moments, and handing one
  back to `moment.utc` parses nothing but still builds a second object, once
  per point -- and it must not change what comes out.
*/

describe("normalising an x value for a time axis", () => {
  const at = Date.UTC(2024, 2, 5, 9, 30);

  test.each([
    ["a moment, which is what a result cell holds", moment.utc(at)],
    ["a Date", new Date(at)],
    ["an ISO string with a zone", "2024-03-05T09:30:00Z"],
    ["an ISO string without one, read as UTC", "2024-03-05T09:30:00"],
    ["epoch milliseconds", at],
  ])("%s all come out as the same instant", (_name, value) => {
    expect(normalizeX(value, "time")).toBe(at);
  });

  test("a moment in a local-time mode still reports its instant", () => {
    expect(normalizeX(moment(at), "time")).toBe(at);
  });

  test("what is not a time is null, rather than a wrong number", () => {
    expect(normalizeX("acme-corp", "time")).toBeNull();
    expect(normalizeX(moment.utc("nonsense"), "time")).toBeNull();
    expect(normalizeX(new Date("nonsense"), "time")).toBeNull();
  });

  test("a category axis gets the formatted time, not a number", () => {
    expect(normalizeX(moment.utc(at), "category")).toBe("2024-03-05 09:30:00");
  });
});
