import chartOptions from "@/visualizations/chart/getOptions";
import cohortOptions from "@/visualizations/cohort/getOptions";
import funnelOptions from "@/visualizations/funnel/getOptions";
import choroplethOptions from "@/visualizations/choropleth/getOptions";
import { formatValue } from "./format";

/*
  Five visualizations stored a numeral format string and now store the shared
  format. `getOptions` converts on read, which means two things have to hold
  for every one of them: a saved string opens as what it meant, and running
  the conversion again over its own output changes nothing -- because
  `getOptions` runs on every render, not once.
*/

const SUBJECTS: [string, (o: any) => any, string][] = [
  ["chart, numbers", (o) => chartOptions({ globalSeriesType: "column", ...o }).numberFormat, "numberFormat"],
  ["chart, percentages", (o) => chartOptions({ globalSeriesType: "column", ...o }).percentFormat, "percentFormat"],
  ["cohort, numbers", (o) => cohortOptions(o).numberFormat, "numberFormat"],
  ["cohort, percentages", (o) => cohortOptions(o).percentFormat, "percentFormat"],
  ["funnel, numbers", (o) => funnelOptions(o, {}).numberFormat, "numberFormat"],
  ["funnel, percentages", (o) => funnelOptions(o, {}).percentFormat, "percentFormat"],
  ["choropleth", (o) => choroplethOptions(o).valueFormat, "valueFormat"],
];

describe("a saved numeral format string, per visualization", () => {
  test.each(SUBJECTS)("%s is read into the shared format", (_name, read, key) => {
    const format = read({ [key]: "0,0.00" });

    expect(format).toEqual(expect.objectContaining({ style: "number", decimals: 2, minDecimals: 2, grouping: true }));
    expect(formatValue(1234.5, format, "en-US")).toBe("1,234.50");
  });

  test.each(SUBJECTS)("%s survives being read again", (_name, read, key) => {
    const once = read({ [key]: "0,0[.]00" });
    const twice = read({ [key]: once });

    expect(twice).toEqual(once);
  });

  test.each(SUBJECTS)("%s keeps its own default when nothing is saved", (_name, read) => {
    const format = read({});

    expect(typeof format).toBe("object");
    expect(format.style).toBe("number");
  });

  test.each(SUBJECTS)("%s falls back rather than break on a string it cannot read", (_name, read, key) => {
    const format = read({ [key]: "0.0e+0" });

    expect(typeof format).toBe("object");
    expect(formatValue(1234.5, format, "en-US")).toEqual(expect.any(String));
  });
});
