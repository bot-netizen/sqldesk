import { buildTooltipFormatter, tooltipRow } from "./buildOption";
import { createFocusTracker, drawnY, focusedFromItems } from "./followCursor";

/*
  The row under the cursor, in the tooltip.

  Reported from a stacked area of spend by data centre: eight series, the
  hovered band correctly lifted out of the plot, and a tooltip listing all
  eight in identical weight -- so reading the number you hovered for meant
  matching a colour swatch against a band.

  Two things have to hold for the mark to be right, and they are tested
  separately because they fail separately: the row has to be *marked*, and it
  has to be the *right* row on a chart whose series are stacked.
*/

const OPTIONS = { series: {}, numberFormat: "0,0.00", percentFormat: "0.00%" };

function items(count: number, at = 0) {
  return Array.from({ length: count }, (_unused, i) => ({
    seriesIndex: i,
    seriesName: `series ${i}`,
    dataIndex: at,
    marker: "",
    color: `#00000${i}`,
    axisValueLabel: "x",
    value: [at, i * 10],
  }));
}

describe("tooltipRow", () => {
  it("marks the focused row and leaves the rest alone", () => {
    expect(tooltipRow("body", true, "#ff0000")).toContain("font-weight:700");
    expect(tooltipRow("body", false, "#ff0000")).not.toContain("font-weight:700");
  });

  it("carries the series colour as a rule rather than colouring the text", () => {
    const row = tooltipRow("body", true, "#ff0000");
    expect(row).toContain("border-left:3px solid #ff0000");
    // Colouring the text itself would make a pale series harder to read, not
    // easier, which is the opposite of what was asked for.
    expect(row).not.toContain("color:#ff0000;");
  });

  it("reserves the rule's width on every row, so the list does not shift", () => {
    // A focused row that was 3px wider than its neighbours would nudge the
    // whole tooltip sideways as the cursor moved down it.
    expect(tooltipRow("body", false)).toContain("border-left:3px solid transparent");
    expect(tooltipRow("body", true, "#abc")).toContain("padding:1px 5px");
    expect(tooltipRow("body", false)).toContain("padding:1px 5px");
  });

  it("escapes a colour it is handed", () => {
    expect(tooltipRow("body", true, '"><script>alert(1)</script>')).not.toContain("<script>");
  });
});

describe("the tooltip formatter, asked which row is focused", () => {
  it("marks exactly one row, the one the tracker names", () => {
    const focus = { focusedFrom: () => 2 };
    const html = buildTooltipFormatter(OPTIONS, false, null, focus)(items(4));

    const bold = html.split("<div").filter((chunk: string) => chunk.includes("font-weight:700"));
    expect(bold).toHaveLength(1);
    expect(bold[0]).toContain("series 2");
  });

  it("marks nothing when the cursor is near no line", () => {
    const html = buildTooltipFormatter(OPTIONS, false, null, { focusedFrom: () => null })(items(4));
    expect(html).not.toContain("font-weight:700");
  });

  it("marks nothing when no tracker is wired in at all", () => {
    // Every other caller of buildOption -- the tests, the thumbnailer -- gets
    // the tooltip it always had.
    const html = buildTooltipFormatter(OPTIONS, false, null)(items(4));
    expect(html).not.toContain("font-weight:700");
    expect(html).toContain("series 0");
  });

  it("still renders every row when the tracker throws", () => {
    const focus = {
      focusedFrom: () => {
        throw new Error("chart disposed");
      },
    };
    const html = buildTooltipFormatter(OPTIONS, false, null, focus)(items(3));
    expect(html).toContain("series 0");
    expect(html).toContain("series 2");
    expect(html).not.toContain("font-weight:700");
  });

  it("leaves a single-item tooltip alone", () => {
    // A pie or a box has one thing under the pointer; there is nothing to
    // pick out, and `params` is not an array there.
    const one = items(1)[0];
    const html = buildTooltipFormatter(OPTIONS, false, null, { focusedFrom: () => 0 })(one);
    expect(html).not.toContain("font-weight:700");
  });
});

describe("drawnY", () => {
  function chartWith(points: number[] | null, itemLayout?: any) {
    return {
      getModel: () => ({
        getSeriesByIndex: () => ({
          getData: () => ({
            getLayout: (key: string) => (key === "points" ? points : null),
            getItemLayout: () => itemLayout,
          }),
        }),
      }),
      convertToPixel: () => [0, 999],
    };
  }

  it("reads the drawn position out of the point array", () => {
    // [x0,y0, x1,y1, x2,y2] -- dataIndex 2 is y = 300.
    expect(drawnY(chartWith([0, 100, 10, 200, 20, 300]), 0, 2)).toBe(300);
  });

  it("is the stacked position, not the raw value", () => {
    /*
      This is the whole reason the point array is read rather than the value
      converted. `pointsLayout` substitutes the stack result dimension before
      projecting, so a band in a stacked area is drawn at its cumulative
      height. A chart whose series each report 10 but are drawn at 100, 200
      and 300 is exactly the stacked case, and measuring the cursor against
      the raw 10 would pick a line that is nowhere on screen.
    */
    const stacked = chartWith([0, 100, 10, 200, 20, 300]);
    expect(drawnY(stacked, 0, 1, [10, 10])).toBe(200);
    expect(drawnY(stacked, 0, 1, [10, 10])).not.toBe(999);
  });

  it("falls back to a bar's own rectangle", () => {
    expect(drawnY(chartWith(null, { x: 5, y: 42, width: 3, height: 9 }), 0, 0)).toBe(42);
  });

  it("falls back to converting the raw point when there is no layout at all", () => {
    expect(drawnY(chartWith(null, null), 0, 0, [1, 2])).toBe(999);
  });

  it("returns null rather than throwing on a disposed chart", () => {
    const dead = {
      getModel: () => {
        throw new Error("disposed");
      },
      convertToPixel: () => {
        throw new Error("disposed");
      },
    };
    expect(drawnY(dead, 0, 0, [1, 2])).toBeNull();
  });
});

describe("focusedFromItems", () => {
  // Three series drawn at y = 100, 200 and 300.
  const chart = {
    getModel: () => ({
      getSeriesByIndex: (i: number) => ({
        getData: () => ({
          getLayout: () => [0, (i + 1) * 100],
          getItemLayout: () => null,
        }),
      }),
    }),
    convertToPixel: () => null,
  };

  it("picks the series the cursor is nearest", () => {
    expect(focusedFromItems(chart, items(3), 205)).toBe(1);
    expect(focusedFromItems(chart, items(3), 95)).toBe(0);
  });

  it("picks nothing when the cursor is far from every line", () => {
    expect(focusedFromItems(chart, items(3), 900)).toBeNull();
  });
});

describe("the tracker", () => {
  it("answers nothing until a chart has installed a resolver", () => {
    const focus = createFocusTracker();
    focus.cursorY = 100;
    expect(focus.focusedFrom(items(3))).toBeNull();
  });

  it("answers nothing while the cursor is off the chart", () => {
    const focus = createFocusTracker();
    focus.resolve = () => 1;
    focus.cursorY = null;
    expect(focus.focusedFrom(items(3))).toBeNull();
  });

  it("answers nothing on a chart with a single series", () => {
    // There is nothing to tell apart, so marking the only row would be noise.
    const focus = createFocusTracker();
    focus.resolve = () => 0;
    focus.cursorY = 10;
    expect(focus.focusedFrom(items(1))).toBeNull();
  });

  it("answers from the resolver once both are set", () => {
    const focus = createFocusTracker();
    focus.resolve = () => 2;
    focus.cursorY = 10;
    expect(focus.focusedFrom(items(3))).toBe(2);
  });
});
