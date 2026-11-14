import QueryResult, {
  isDateTime,
  NO_REASON,
  NO_RESULT_STORED,
  pollFailedMessage,
  resultLoadFailedMessage,
} from "@/services/query-result";
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

/*
  Whenever a result is not shown, the page says why and what to do. A failure
  with no words read as a query that finished and found nothing.
*/
describe("never a silent failure", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(Auth, "isAuthenticated").mockReturnValue(true);
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  async function settle() {
    for (let i = 0; i < 5; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await Promise.resolve();
    }
  }

  function watched(result) {
    result.toPromise().catch(() => {});
    return result;
  }

  test("a failure with no reason gets one", () => {
    const result = watched(new QueryResult({ job: { id: "j1", status: 4, error: "" } }));
    expect(result.getStatus()).toBe("failed");
    expect(result.getError()).toBe(NO_REASON);
  });

  test("a failure's own reason is kept", () => {
    const result = watched(new QueryResult({ job: { id: "j1", status: 4, error: "Table x does not exist" } }));
    expect(result.getError()).toBe("Table x does not exist");
  });

  test("a job that finished with nothing stored stops waiting and says so", async () => {
    const result = watched(new QueryResult({ job: { id: "j1", status: 2 } }));
    jest
      .spyOn(axios, "get")
      .mockImplementation(() => Promise.resolve({ job: { id: "j1", status: 3, query_result_id: null } }));

    result.refreshStatus(1, {});
    await settle();

    expect(result.getStatus()).toBe("failed");
    expect(result.getError()).toBe(NO_RESULT_STORED);
    jest.advanceTimersByTime(60000);
    await settle();
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test("a result that cannot be loaded says why, not 'check your Internet'", () => {
    const tooBig = resultLoadFailedMessage({ response: { status: 504 } });
    expect(tooBig).toContain("did not answer in time (HTTP 504)");
    expect(tooBig).toContain("LIMIT");
    expect(resultLoadFailedMessage({})).toContain("no answer reached the browser");
    expect(pollFailedMessage({ response: { status: 502 } })).toContain("may still be running");
  });
});
