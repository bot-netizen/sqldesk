import QueryResult, { isDateTime } from "@/services/query-result";
import { axios } from "@/services/axios";
import { Auth } from "@/services/auth";

describe("isDateTime", () => {
  it.each([
    ["2022-01-01T00:00:00", true],
    ["2022-01-01T00:00:00+09:00", true],
    ["2021-01-27T00:00:01.733983944+03:00 stderr F {", false],
    // Date-shaped but not a date: the shape test alone is not enough, so
    // moment still has to be asked about anything that gets past it.
    ["2022-13-45T00:00:00", false],
    ["2021-01-27Z00:00:00+09:00", false],
    ["2021-01-27", false],
    ["foo bar", false],
    [2022, false],
    [null, false],
    ["", false],
  ])("isDateTime('%s'). expected '%s'.", (value, expected) => {
    expect(isDateTime(value)).toBe(expected);
  });
});

/*
  Asking after a running query. One failed poll -- a 502 while a deploy rolls,
  a dropped connection -- used to mark the query failed while it ran on; and
  polling never stopped when the page that asked had gone.
*/
describe("polling a running query", () => {
  const RUNNING = { job: { id: "j1", status: 2 } };

  function rejected(status) {
    return Promise.reject(Object.assign(new Error("Request failed"), { response: { status } }));
  }

  beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(Auth, "isAuthenticated").mockReturnValue(true);
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  // A failed result rejects its promise; caught here so the test sees the
  // status rather than an unhandled rejection.
  function watched(result) {
    result.toPromise().catch(() => {});
    return result;
  }

  async function settle() {
    for (let i = 0; i < 5; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await Promise.resolve();
    }
  }

  test("a failed poll is asked again rather than failing the query", async () => {
    const result = watched(new QueryResult(RUNNING));
    jest
      .spyOn(axios, "get")
      .mockImplementationOnce(() => rejected(502))
      .mockImplementation(() => Promise.resolve({ job: { id: "j1", status: 2 } }));

    result.refreshStatus(1, {});
    await settle();
    expect(result.getStatus()).not.toBe("failed");

    jest.advanceTimersByTime(1000);
    await settle();
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(result.getStatus()).not.toBe("failed");
  });

  test("but after five in a row it says so", async () => {
    const result = watched(new QueryResult(RUNNING));
    jest.spyOn(axios, "get").mockImplementation(() => rejected(502));

    result.refreshStatus(1, {});
    for (let attempt = 0; attempt < 6; attempt += 1) {
      // eslint-disable-next-line no-await-in-loop
      await settle();
      jest.advanceTimersByTime(60000);
    }
    await settle();

    expect(result.getStatus()).toBe("failed");
    expect(axios.get).toHaveBeenCalledTimes(6);
  });

  test("a job that is not there is an answer, not a blip", async () => {
    const result = watched(new QueryResult(RUNNING));
    jest.spyOn(axios, "get").mockImplementation(() => rejected(404));

    result.refreshStatus(1, {});
    await settle();

    expect(result.getStatus()).toBe("failed");
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test("an abandoned result is not asked after again", async () => {
    const result = watched(new QueryResult(RUNNING));
    jest.spyOn(axios, "get").mockImplementation(() => Promise.resolve({ job: { id: "j1", status: 2 } }));

    result.refreshStatus(1, {});
    await settle();
    result.abandon();
    jest.advanceTimersByTime(60000);
    await settle();

    expect(axios.get).toHaveBeenCalledTimes(1);
  });
});
