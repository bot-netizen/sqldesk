import { retryImport, isChunkLoadError, RELOAD_KEY, RELOAD_WINDOW } from "./lazyPage";

/*
  What this has to get right is the difference between the two failures it
  covers: a request that was dropped (ask again) and a chunk that a deploy
  took away (ask again from a fresh index.html). Getting the second one wrong
  in the other direction -- reloading whenever an import fails -- turns a bad
  deploy into a reload loop, so the one-reload guard is pinned too.
*/

function fakeStorage(initial = {}) {
  const values = { ...initial };
  return {
    getItem: (key) => (key in values ? values[key] : null),
    setItem: (key, value) => {
      values[key] = String(value);
    },
    values,
  };
}

function chunkError() {
  const error = new Error("Loading chunk admin failed.");
  error.name = "ChunkLoadError";
  return error;
}

const seams = (overrides) => ({
  delay: 0,
  wait: () => Promise.resolve(),
  storage: fakeStorage(),
  reload: jest.fn(),
  now: () => 1000,
  ...overrides,
});

describe("retryImport", () => {
  test("a chunk that loads is loaded once", async () => {
    const load = jest.fn(() => Promise.resolve("page"));

    await expect(retryImport(load, seams())).resolves.toBe("page");
    expect(load).toHaveBeenCalledTimes(1);
  });

  test("a dropped request is asked for again, and the page arrives", async () => {
    const load = jest
      .fn()
      .mockRejectedValueOnce(new Error("NetworkError when attempting to fetch resource"))
      .mockResolvedValue("page");

    await expect(retryImport(load, seams())).resolves.toBe("page");
    expect(load).toHaveBeenCalledTimes(2);
  });

  test("a chunk a deploy took away reloads the page, once", async () => {
    const load = jest.fn(() => Promise.reject(chunkError()));
    const reload = jest.fn();
    const storage = fakeStorage();
    let settled = false;

    retryImport(load, seams({ load, reload, storage })).then(
      () => {
        settled = true;
      },
      () => {
        settled = true;
      }
    );
    await Promise.resolve().then().then().then().then().then().then();

    expect(reload).toHaveBeenCalledTimes(1);
    expect(storage.values[RELOAD_KEY]).toBe("1000");
    // Settling would render the rejection in the moment before the page goes.
    expect(settled).toBe(false);
  });

  test("after a reload the same failure is reported rather than reloading again", async () => {
    const load = jest.fn(() => Promise.reject(chunkError()));
    const reload = jest.fn();
    const storage = fakeStorage({ [RELOAD_KEY]: "1000" });

    await expect(retryImport(load, seams({ reload, storage, now: () => 1000 + RELOAD_WINDOW - 1 }))).rejects.toThrow(
      "Loading chunk"
    );
    expect(reload).not.toHaveBeenCalled();
  });

  test("a reload from a previous session does not count", async () => {
    const load = jest.fn(() => Promise.reject(chunkError()));
    const reload = jest.fn();
    const storage = fakeStorage({ [RELOAD_KEY]: "1000" });

    retryImport(load, seams({ reload, storage, now: () => 1000 + RELOAD_WINDOW + 1 }));
    await Promise.resolve().then().then().then().then().then().then();

    expect(reload).toHaveBeenCalledTimes(1);
  });

  test("a page that throws while it initialises is reported, not reloaded", async () => {
    const load = jest.fn(() => Promise.reject(new TypeError("x is not a function")));
    const reload = jest.fn();

    await expect(retryImport(load, seams({ reload }))).rejects.toThrow("x is not a function");
    expect(reload).not.toHaveBeenCalled();
    expect(load).toHaveBeenCalledTimes(3); // the first ask and two retries
  });
});

describe("isChunkLoadError", () => {
  test.each([
    ["webpack's own error", chunkError()],
    ["a stylesheet chunk", Object.assign(new Error("Loading CSS chunk 3 failed"), { code: "CSS_CHUNK_LOAD_FAILED" })],
    ["a native module failure", new TypeError("Failed to fetch dynamically imported module: /app/admin.js")],
  ])("recognises %s", (_what, error) => {
    expect(isChunkLoadError(error)).toBe(true);
  });

  test.each([
    ["a programming error", new TypeError("x is not a function")],
    ["an API failure", Object.assign(new Error("Request failed with status code 500"), { isAxiosError: true })],
    ["nothing at all", null],
  ])("leaves %s alone", (_what, error) => {
    expect(isChunkLoadError(error)).toBe(false);
  });
});
