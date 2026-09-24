import React from "react";
import { mount } from "enzyme";
import MarkdownEditor from "./MarkdownEditor";

const render = (props = {}) => mount(<MarkdownEditor value="" onChange={() => {}} {...props} />);
const tab = (w, name) =>
  w
    .find(".ant-tabs-tab")
    .filterWhere((n) => n.text() === name)
    .first();
const preview = (w) => w.find('[data-test="MarkdownEditor.Preview"]').first();

/*
  What the tabs are for: markdown that is only ever seen as markdown is
  markdown you find out about after saving it.
*/

describe("seeing markdown before saving it", () => {
  test("opens on the text, not the picture of it", () => {
    const w = render({ value: "## Heading" });
    expect(w.find("textarea").props().value).toBe("## Heading");
    expect(preview(w).length).toBe(0);
  });

  test("the preview shows what the markdown becomes", () => {
    const w = render({ value: "## Heading\n\n| a | b |\n|---|---|\n| 1 | 2 |" });
    tab(w, "Preview").simulate("click");
    const html = preview(w).html();
    expect(html).toContain("<h2");
    expect(html).toContain("<table");
  });

  test("and says so plainly when there is nothing yet", () => {
    const w = render({ value: "" });
    tab(w, "Preview").simulate("click");
    expect(preview(w).text()).toContain("Nothing to preview");
  });

  test("typing reports the new text", () => {
    const onChange = jest.fn();
    const w = render({ onChange });
    w.find("textarea").simulate("change", { target: { value: "written" } });
    expect(onChange).toHaveBeenCalledWith("written");
  });

  test("the text survives a trip to the preview and back", () => {
    // Kept mounted rather than rebuilt: coming back to a box scrolled to the
    // top with the caret lost is worse than no preview at all.
    const w = render({ value: "kept" });
    tab(w, "Preview").simulate("click");
    tab(w, "Write").simulate("click");
    expect(w.find("textarea").props().value).toBe("kept");
  });

  test("the preview carries the styling the saved thing will have", () => {
    // Not a likeness of the widget -- the widget, drawn early.
    const w = render({ value: "words", previewClassName: "preview-plain", previewStyle: { textAlign: "center" } });
    tab(w, "Preview").simulate("click");
    expect(preview(w).hasClass("preview-plain")).toBe(true);
    expect(preview(w).props().style.textAlign).toBe("center");
  });

  test("raw HTML survives, because that is the point of allowing it", () => {
    const w = render({ value: '<div style="display:flex">two columns</div>' });
    tab(w, "Preview").simulate("click");
    expect(preview(w).html()).toContain("display:flex");
  });

  test("but a script tag does not", () => {
    const w = render({ value: "<script>window.pwned = 1</script>ok" });
    tab(w, "Preview").simulate("click");
    expect(preview(w).html()).not.toContain("<script");
  });
});
