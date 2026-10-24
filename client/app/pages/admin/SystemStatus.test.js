import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";

/*
  The system status page refreshes itself every minute, and is read when
  something is already wrong -- so a refresh that fails must leave the figures
  on screen rather than handing the page to the error boundary. That it keeps
  polling afterwards is what lets it recover on its own.
*/
jest.mock("@/services/recordEvent", () => jest.fn());

const mockGet = jest.fn();
jest.mock("@/services/axios", () => ({ axios: { get: (...args) => mockGet(...args) } }));

// eslint-disable-next-line import/first
import SystemStatus from "./SystemStatus";

const STATUS = {
  version: "0.7.7",
  manager: { started_at: 1, last_refresh_at: 2, outdated_queries_count: 0, queues: { queries: { size: 0 } } },
  database_metrics: { metrics: [["Query count", 12]] },
  workers: [],
};

describe("admin System Status", () => {
  let logged;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    logged = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.useRealTimers();
    logged.mockRestore();
  });

  async function render(onError = jest.fn()) {
    let wrapper;
    await act(async () => {
      wrapper = mount(<SystemStatus onError={onError} />);
    });
    wrapper.update();
    return wrapper;
  }

  test("a failed refresh keeps the page, and says the figures are old", async () => {
    mockGet.mockResolvedValueOnce(STATUS).mockRejectedValueOnce(new Error("Bad gateway"));
    const onError = jest.fn();
    const shown = await render(onError);
    expect(shown.find('[data-test="StaleNotice"]').exists()).toBe(false);

    await act(async () => {
      jest.advanceTimersByTime(60 * 1000);
      await Promise.resolve();
      await Promise.resolve();
    });
    shown.update();

    expect(shown.find('[data-test="StaleNotice"]').exists()).toBe(true);
    expect(shown.text()).toContain("Query count");
    expect(onError).not.toHaveBeenCalled();
  });

  test("and the next refresh that works takes the notice away", async () => {
    mockGet.mockResolvedValueOnce(STATUS).mockRejectedValueOnce(new Error("Bad gateway")).mockResolvedValue(STATUS);
    const shown = await render();

    for (let tick = 0; tick < 2; tick += 1) {
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        jest.advanceTimersByTime(60 * 1000);
        await Promise.resolve();
        await Promise.resolve();
      });
    }
    shown.update();

    expect(shown.find('[data-test="StaleNotice"]').exists()).toBe(false);
  });

  test("the first load failing is still the error boundary's business", async () => {
    const error = new Error("Internal server error");
    mockGet.mockRejectedValue(error);
    const onError = jest.fn();

    await render(onError);

    expect(onError).toHaveBeenCalledWith(error);
  });
});
