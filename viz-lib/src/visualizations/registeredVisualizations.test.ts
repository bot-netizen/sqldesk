import fs from "fs";
import path from "path";
import registeredVisualizations, { loadVisualization } from "./registeredVisualizations";

/*
  The registry is what every page loads, whether or not it ever draws a chart.
  It is allowed to know a visualization's name and size; it is not allowed to
  reach its drawing code, because that drags in ECharts, Leaflet and a pivot
  table for a login screen.

  That property is one static import away from being lost, and losing it is
  invisible -- the app still works, it is just megabytes heavier. So it is
  checked here rather than left to a bundle report nobody runs.
*/

const here = __dirname;

function read(file: string) {
  return fs.readFileSync(path.join(here, file), "utf8");
}

/** Every directory holding a visualization, found rather than listed. */
const visualizationDirs = fs
  .readdirSync(here, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && fs.existsSync(path.join(here, entry.name, "index.ts")))
  .map((entry) => entry.name)
  .filter((name) => /^\s*export default \{[\s\S]*\btype:/m.test(read(path.join(name, "index.ts"))));

describe("the visualization registry", () => {
  test("registers every visualization in the folder", () => {
    expect(visualizationDirs.length).toBe(18);
    expect(Object.keys(registeredVisualizations).length).toBe(visualizationDirs.length);
  });

  test.each(visualizationDirs)("%s declares a loader instead of importing its components", (dir) => {
    const source = read(path.join(dir, "index.ts"));
    expect(source).toMatch(/load: \(\) => import\(\/\* webpackChunkName: "viz-[a-z-]+" \*\/ "\.\/components"\)/);
    // The two that would pull the whole visualization into the registry.
    expect(source).not.toMatch(/^import .* from "\.\/Renderer";$/m);
    expect(source).not.toMatch(/^import .* from "\.\/Editor";$/m);
  });

  test("every entry carries what a menu and a dashboard grid need, without components", () => {
    Object.values(registeredVisualizations).forEach((config: any) => {
      expect(typeof config.type).toBe("string");
      expect(typeof config.name).toBe("string");
      expect(typeof config.getOptions).toBe("function");
      expect(typeof config.load).toBe("function");
      // Present eagerly, these would be the drawing code itself.
      expect(config.Renderer).toBeUndefined();
      expect(config.Editor).toBeUndefined();
    });
  });

  test("getOptions works without loading anything", () => {
    // The visualization editor and the dashboard both call this before there
    // is anything on screen, so it has to stay synchronous.
    Object.values(registeredVisualizations).forEach((config: any) => {
      expect(() => config.getOptions({}, { columns: [], rows: [] })).not.toThrow();
    });
  });

  test("loading the same visualization twice fetches it once", async () => {
    // A stand-in rather than a real type: jest cannot require ECharts, and
    // what is under test here is the caching, not any one visualization.
    const components = { Renderer: () => null, Editor: () => null };
    const load = jest.fn(() => Promise.resolve(components));
    (registeredVisualizations as any).FAKE = { type: "FAKE", name: "Fake", getOptions: (o: any) => o, load };
    try {
      // Both in flight at once: the second must join the first, not start a
      // second fetch of the same chunk.
      const [first, second] = await Promise.all([loadVisualization("FAKE"), loadVisualization("FAKE")]);
      expect(first).toBe(components);
      expect(second).toBe(components);
      // And once resolved it is remembered, so a later call never suspends.
      await loadVisualization("FAKE");
      expect(load).toHaveBeenCalledTimes(1);
    } finally {
      delete (registeredVisualizations as any).FAKE;
    }
  });

  test("a failed fetch is not remembered as a failure", async () => {
    const components = { Renderer: () => null };
    // A chunk can 404 because a deploy landed mid-session; the next try may
    // well succeed, and caching the rejection would break the tab until reload.
    const load = jest
      .fn()
      .mockRejectedValueOnce(new Error("chunk load failed"))
      .mockResolvedValueOnce(components as any);
    (registeredVisualizations as any).FLAKY = { type: "FLAKY", name: "Flaky", getOptions: (o: any) => o, load };
    try {
      await expect(loadVisualization("FLAKY")).rejects.toThrow("chunk load failed");
      await expect(loadVisualization("FLAKY")).resolves.toBe(components);
      expect(load).toHaveBeenCalledTimes(2);
    } finally {
      delete (registeredVisualizations as any).FLAKY;
    }
  });

  test("an unknown type rejects rather than throwing where nobody can catch it", async () => {
    await expect(loadVisualization("NOT_A_VISUALIZATION")).rejects.toThrow(/not registered/);
  });
});
