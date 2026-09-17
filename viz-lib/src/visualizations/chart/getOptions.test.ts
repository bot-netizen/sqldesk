import getOptions from "./getOptions";
import buildOption from "./echarts/buildOption";
import { DEFAULT_COLOR_SCHEME, resolveColorScheme } from "@/visualizations/ColorPalette";

describe("Visualizations -> Chart -> color scheme", () => {
  test("charts saved under either former name resolve to the default palette", () => {
    // This project has been renamed twice, and the default palette carries the
    // product's name, so a saved chart can hold any of the three.
    expect(getOptions({ color_scheme: "Redash" }).color_scheme).toBe("SQLDesk");
    expect(getOptions({ color_scheme: "Tealdash" }).color_scheme).toBe("SQLDesk");
  });

  test("existing palette names are left alone", () => {
    expect(getOptions({ color_scheme: "Viridis" }).color_scheme).toBe("Viridis");
    expect(resolveColorScheme("Tableau 10")).toBe("Tableau 10");
  });

  test("an unknown or missing scheme falls back instead of throwing", () => {
    expect(resolveColorScheme("No Such Palette")).toBe(DEFAULT_COLOR_SCHEME);
    expect(resolveColorScheme(undefined)).toBe(DEFAULT_COLOR_SCHEME);
    expect(resolveColorScheme(null)).toBe(DEFAULT_COLOR_SCHEME);
  });

  test("new charts get the default scheme", () => {
    expect(getOptions({}).color_scheme).toBe(DEFAULT_COLOR_SCHEME);
  });
});

describe("Visualizations -> Chart -> legacy color scheme rendering", () => {
  const chartData = [
    {
      name: "a",
      type: "column",
      data: [
        { x: "x1", y: 10, $raw: {} },
        { x: "x2", y: 20, $raw: {} },
      ],
    },
  ];

  // Deliberately NOT through getOptions: that normalises the name on the way in,
  // which is the first line of defence and is covered above. This is the second
  // one -- options can reach the renderer from a saved visualization or the API
  // without passing through it, and an unresolvable name used to index the
  // palette table to `undefined`, whose `.length` took down the whole dashboard.
  function buildWithScheme(colorScheme: string) {
    const options = {
      ...getOptions({ globalSeriesType: "column" }),
      // No explicit series colour, so the palette is actually consulted. With
      // one set, the lookup short-circuits and the crash never reproduces.
      seriesOptions: {},
      color_scheme: colorScheme,
    };
    return buildOption(chartData, options);
  }

  test("a chart saved with either old scheme name renders instead of throwing", () => {
    expect(() => buildWithScheme("Redash")).not.toThrow();
    expect(() => buildWithScheme("Tealdash")).not.toThrow();
  });

  test("a scheme that does not exist at all still renders", () => {
    expect(() => buildWithScheme("No Such Palette")).not.toThrow();
  });

  test("either old scheme name renders exactly like the new one", () => {
    for (const formerName of ["Redash", "Tealdash"]) {
      expect(buildWithScheme(formerName).option.color).toEqual(buildWithScheme("SQLDesk").option.color);
      expect(buildWithScheme(formerName).option.series[0].itemStyle).toEqual(
        buildWithScheme("SQLDesk").option.series[0].itemStyle
      );
    }
  });
});
