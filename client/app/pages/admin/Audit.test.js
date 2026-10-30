import React from "react";
import { shallow } from "enzyme";
import { Sparkline, count } from "./Audit";

/*
  The audit page's own small pieces.

  The page is three antd tables around numbers the server worked out, so what
  is worth testing here is the two things this file decides for itself: how a
  count reads, and how a run of days draws when there are two of them rather
  than ninety.
*/

describe("a count somebody reads", () => {
  it("groups the digits", () => {
    expect(count(4200000)).toBe("4,200,000");
  });

  it("is zero rather than blank when nothing ran", () => {
    expect(count(0)).toBe("0");
    expect(count(null)).toBe("0");
    expect(count(undefined)).toBe("0");
  });
});

describe("the strip of days", () => {
  it("is nothing at all when there are no days", () => {
    expect(shallow(<Sparkline series={[]} />).isEmptyRender()).toBe(true);
    expect(shallow(<Sparkline series={null} />).isEmptyRender()).toBe(true);
  });

  it("draws one bar a day", () => {
    const strip = shallow(
      <Sparkline
        series={[
          ["2026-10-28", 4],
          ["2026-10-29", 2],
          ["2026-10-30", 8],
        ]}
      />
    );

    expect(strip.find(".audit-sparkline-bar")).toHaveLength(3);
  });

  it("scales the bars against the busiest day, not against a fixed number", () => {
    const strip = shallow(
      <Sparkline
        series={[
          ["2026-10-29", 5],
          ["2026-10-30", 10],
        ]}
      />
    );
    const heights = strip.find(".audit-sparkline-bar").map((bar) => bar.prop("style").height);

    expect(heights).toEqual(["50%", "100%"]);
  });

  it("gives a day with nothing on it a bar you can still see", () => {
    // Zero height would be no bar at all, and a gap in the run reads as a day
    // that was not recorded rather than a day with no executions.
    const strip = shallow(
      <Sparkline
        series={[
          ["2026-10-29", 0],
          ["2026-10-30", 100],
        ]}
      />
    );

    expect(strip.find(".audit-sparkline-bar").at(0).prop("style").height).toBe("2%");
  });

  it("says the day and the count on hover, because the bars carry no labels", () => {
    const strip = shallow(<Sparkline series={[["2026-10-30", 4200]]} />);

    expect(strip.find(".audit-sparkline-bar").prop("title")).toBe("2026-10-30: 4,200");
  });
});
