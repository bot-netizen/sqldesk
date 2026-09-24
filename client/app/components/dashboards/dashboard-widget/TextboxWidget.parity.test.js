import React from "react";
import { mount } from "enzyme";
import TextboxWidget from "./TextboxWidget";

const TEXT = ["# Heading", "", "| a | b |", "|---|---|", "| 1 | 2 |", "", "- one", "- ~~two~~"].join("\n");

const widgetOf = (options) => ({
  id: 7,
  width: 1,
  text: TEXT,
  options: { position: { col: 0, row: 0, sizeX: 6, sizeY: 4 }, ...options },
  save: () => Promise.resolve(),
});

const render = (options, props) => mount(<TextboxWidget widget={widgetOf(options)} {...props} />);
const body = (w) => w.find("div.markdown");
const tile = (w) => w.find(".tile").first();

/*
  A dashboard has to look the same whether it is being read by the person who
  saved it or by somebody following a published link. The two pages are
  separate components, and the widget is the only thing they have in common,
  so this is where that can be pinned.

  Not pinned: the controls. A public viewer cannot edit or refresh a widget,
  so the buttons that do those things are genuinely absent -- and they only
  appear on hover to begin with.
*/

describe("a widget reads the same saved as published", () => {
  const cases = [
    ["a plain section heading", { textStyle: "plain", align: "center" }],
    ["a card", { textStyle: "card", align: "left" }],
    ["one saved before there were styles at all", {}],
  ];

  test.each(cases)("%s draws identically", (_name, options) => {
    const saved = render(options, { canEdit: true, isPublic: false });
    const published = render(options, { canEdit: false, isPublic: true });

    expect(body(published).html()).toBe(body(saved).html());
    expect(tile(published).prop("className")).toBe(tile(saved).prop("className"));
  });

  test("the markdown is the markdown, not the source", () => {
    // The whole point of the styling: if this ever renders as text the two
    // sides above would still agree, and agree on being wrong.
    const html = body(render({}, {})).html();
    expect(html).toContain("<h1");
    expect(html).toContain("<table");
    expect(html).toContain("<del");
  });

  test("a plain textbox loses its tile on both", () => {
    expect(tile(render({ textStyle: "plain" }, { isPublic: true })).hasClass("widget-text-plain")).toBe(true);
    expect(tile(render({ textStyle: "plain" }, { isPublic: false })).hasClass("widget-text-plain")).toBe(true);
  });

  test("alignment reaches the page on both", () => {
    expect(body(render({ align: "right" }, { isPublic: true })).prop("style").textAlign).toBe("right");
    expect(body(render({ align: "right" }, { isPublic: false })).prop("style").textAlign).toBe("right");
  });
});
