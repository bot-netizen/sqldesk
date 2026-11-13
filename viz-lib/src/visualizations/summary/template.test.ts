import { evaluate, matches, parseExpression, render, resolveColumn, split, starterTemplate } from "./template";

/*
  A sentence with the query's numbers in it, worked out the same way every
  time the query refreshes -- and saying so, in place, when it cannot be.
*/

const data = {
  columns: [
    { name: "region", type: "string" },
    { name: "revenue", type: "float" },
    { name: "orders", type: "integer" },
    { name: "change", type: "float" },
    { name: "status", type: "string" },
  ],
  rows: [
    { region: "East", revenue: 412000.5, orders: 1200, change: 0.124, status: "healthy" },
    { region: "West", revenue: 84000, orders: 300, change: -0.081, status: "degraded" },
    { region: "North", revenue: 514000, orders: 1500, change: 0.02, status: "healthy" },
  ],
};

function text(source: string, rules: any[] = []) {
  const piece = evaluate(source, data, rules);
  return piece.text;
}

describe("Summary: splitting a template", () => {
  it("keeps the words and the values in order", () => {
    expect(split("Revenue is {{ revenue }}, from {{ orders }}.")).toEqual([
      { kind: "text", text: "Revenue is " },
      { kind: "expression", text: "revenue" },
      { kind: "text", text: ", from " },
      { kind: "expression", text: "orders" },
      { kind: "text", text: "." },
    ]);
  });

  it("is words alone when there is nothing to fill in", () => {
    expect(split("Nothing to see.")).toEqual([{ kind: "text", text: "Nothing to see." }]);
    expect(split("")).toEqual([]);
  });
});

describe("Summary: what a value is", () => {
  it("is the first row's by default", () => {
    expect(text("region")).toBe("East");
  });

  it("is a total over every row", () => {
    expect(text("sum(orders)")).toBe("3,000");
    expect(text("max(revenue)")).toBe("514,000");
    expect(text("min(change)")).toBe("-0.08");
    expect(text("count()")).toBe("3");
  });

  it("is one row, found by another column", () => {
    expect(text('revenue where region = "West"')).toBe("84,000");
    expect(text("revenue where region = West")).toBe("84,000");
    expect(text("sum(orders) where status = healthy")).toBe("2,700");
    expect(text('count() where status != "healthy"')).toBe("1");
  });

  it("is a dash where there is nothing to show", () => {
    expect(text('revenue where region = "Mars"')).toBe("—");
    expect(evaluate("revenue", { columns: data.columns, rows: [] }).text).toBe("—");
  });

  it("finds a column whatever its case", () => {
    expect(text("REVENUE | integer")).toBe("412,001");
  });
});

describe("Summary: formats", () => {
  it("formats money, fractions and numbers", () => {
    expect(text("revenue | currency")).toBe("$412,000.5");
    expect(text("revenue | currency(€)")).toBe("€412,000.5");
    expect(text('revenue where region = "West" | currency')).toBe("$84,000");
    expect(text("change | percent")).toBe("12.4%");
    expect(text("revenue | round(1)")).toBe("412,000.5");
    expect(text("revenue | integer")).toBe("412,001");
  });

  it("puts a minus before the symbol, as money is written", () => {
    expect(evaluate("x | currency", { columns: [{ name: "x", type: "float" }], rows: [{ x: -12.5 }] }).text).toBe(
      "-$12.5"
    );
  });

  it("marks the direction with an arrow", () => {
    expect((evaluate("change | percent | arrow", data) as any).icon).toBe("up");
    expect((evaluate('change where region = "West" | arrow', data) as any).icon).toBe("down");
  });

  it("changes case", () => {
    expect(text("status | upper")).toBe("HEALTHY");
  });
});

describe("Summary: rules", () => {
  const rules = [
    { column: "change", op: ">=", value: "0", tone: "good", icon: "up" },
    { column: "change", op: "<", value: "0", tone: "bad", icon: "down" },
    { column: "status", op: "=", value: "degraded", tone: "bad", icon: "alert" },
    { column: "orders", op: "between", value: "100", value2: "500", tone: "watch" },
  ];

  it("colours a value by the first rule that holds", () => {
    expect(evaluate("change", data, rules as any)).toMatchObject({ tone: "good", icon: "up" });
    expect(evaluate('change where region = "West"', data, rules as any)).toMatchObject({
      tone: "bad",
      icon: "down",
    });
  });

  it("compares words without minding their case", () => {
    expect(evaluate('status where region = "West"', data, rules as any)).toMatchObject({ tone: "bad" });
    expect(matches({ column: "s", op: "=", value: "Degraded", tone: "bad" }, "degraded")).toBe(true);
  });

  it("holds a between at both ends", () => {
    const between = { column: "x", op: "between", value: 100, value2: 500, tone: "watch" } as any;
    expect([99, 100, 300, 500, 501].map((n) => matches(between, n))).toEqual([false, true, true, true, false]);
  });

  it("applies an aggregate's rule by the column inside it", () => {
    const total = [{ column: "orders", op: ">", value: "2000", tone: "good" }];
    expect(evaluate("sum(orders)", data, total as any)).toMatchObject({ tone: "good" });
  });

  it("leaves a value no rule matches plain", () => {
    expect(evaluate("region", data, rules as any)).toMatchObject({ tone: null, icon: null });
  });

  it("never colours a missing value", () => {
    expect(matches({ column: "x", op: "<", value: 0, tone: "bad" }, null)).toBe(false);
  });
});

describe("Summary: problems, said in place", () => {
  it("names a column that is not there, and the one that was probably meant", () => {
    expect(evaluate("revnue", data)).toMatchObject({
      kind: "problem",
      text: "revnue isn't in this result — did you mean revenue?",
    });
  });

  it("does not guess at a name nothing is close to", () => {
    expect(evaluate("temperature", data)).toMatchObject({ kind: "problem", text: "temperature isn't in this result." });
  });

  it("says what a format can be", () => {
    expect(evaluate("revenue | dollars", data).text).toContain("isn't a format");
  });

  it("says an aggregate needs its column", () => {
    expect(parseExpression("sum()")).toBe("sum() needs a column: sum(revenue).");
  });

  it("checks the column a where looks at", () => {
    expect(evaluate('revenue where reigon = "West"', data)).toMatchObject({ kind: "problem" });
    expect(resolveColumn("reigon", data.columns).problem).toContain("did you mean region?");
  });
});

describe("Summary: a whole template", () => {
  it("is words and values in order, never markup", () => {
    const pieces = render("Top: {{ region }} <b>{{ status }}</b>", {
      columns: data.columns,
      rows: [{ region: "<script>alert(1)</script>", status: "ok" }],
    });

    expect(pieces[1]).toMatchObject({ kind: "value", text: "<script>alert(1)</script>" });
    // The value is text; the renderer puts it in a text node, so it is shown,
    // not run.
    expect(pieces.map((piece) => piece.kind)).toEqual(["text", "value", "text", "value", "text"]);
  });

  it("starts a new summary on a sentence that works", () => {
    expect(starterTemplate(data.columns)).toBe("Total revenue is {{ sum(revenue) }} across {{ count() }} rows.");
    expect(starterTemplate([{ name: "name", type: "string" }])).toBe("{{ count() }} rows.");
  });
});

describe("Summary: units", () => {
  it("puts a unit inside the value's colour", () => {
    // Quoted, to keep a space: the brackets are trimmed.
    expect(text(`orders | integer | suffix(" orders")`)).toBe("1,200 orders");
    expect(text("revenue | integer | prefix(~)")).toBe("~412,001");
    expect(
      evaluate("x | number | suffix(%)", { columns: [{ name: "x", type: "float" }], rows: [{ x: 100 }] }).text
    ).toBe("100%");
  });
});
