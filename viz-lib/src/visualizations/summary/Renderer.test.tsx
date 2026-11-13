import React from "react";
import { mount } from "enzyme";
import Renderer, { toLines } from "./Renderer";
import Editor from "./Editor";
import getOptions from "./getOptions";
import { render } from "./template";

const data = {
  columns: [
    { name: "region", type: "string" },
    { name: "revenue", type: "float" },
    { name: "change", type: "float" },
  ],
  rows: [
    { region: "East", revenue: 412000, change: 0.124 },
    { region: "West", revenue: 84000, change: -0.081 },
  ],
};

const rules = [
  { column: "change", op: ">=", value: "0", tone: "good", icon: "up" },
  { column: "change", op: "<", value: "0", tone: "bad", icon: "down" },
];

function draw(options: any) {
  return mount(<Renderer data={data} options={getOptions(options, data)} />);
}

describe("Summary renderer", () => {
  it("writes the sentence with its values coloured by the rules", () => {
    const wrapper = draw({ template: "Revenue {{ sum(revenue) | currency }}, {{ change | percent }}.", rules });

    expect(wrapper.text()).toBe("Revenue $496,000, ▲12.4%.");
    const values = wrapper.find('[data-test="Summary.Value"]');
    expect(values.at(0).hasClass("summary-value--plain")).toBe(true);
    expect(values.at(1).hasClass("summary-value--good")).toBe(true);
  });

  it("shows a problem where the value would have been", () => {
    const wrapper = draw({ template: "Revenue {{ revnue }}." });

    expect(wrapper.find('[data-test="Summary.Problem"]').text()).toContain("did you mean revenue?");
  });

  it("puts a value from the result on the page as text, never as markup", () => {
    const wrapper = mount(
      <Renderer
        data={{ columns: [{ name: "x", type: "string" }], rows: [{ x: "<img src=x onerror=alert(1)>" }] }}
        options={getOptions({ template: "{{ x }}" })}
      />
    );

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.text()).toBe("<img src=x onerror=alert(1)>");
  });

  it("makes each line a bullet", () => {
    const wrapper = draw({
      layout: "bullets",
      template: "East {{ revenue }}\n\nWest {{ revenue where region = West }}",
    });

    expect(wrapper.find("li").map((item) => item.text())).toEqual(["East 412,000", "West 84,000"]);
  });

  it("joins the lines of a status line with a dot", () => {
    const wrapper = draw({ layout: "status", template: "{{ count() }} regions\n{{ change | percent }} up" });

    expect(wrapper.find(".summary-status-item").map((item) => item.text())).toEqual(["2 regions", "12.4% up"]);
    expect(wrapper.find(".summary-separator")).toHaveLength(1);
  });

  it("asks to be written rather than drawing nothing", () => {
    const wrapper = draw({ template: "   " });

    expect(wrapper.find('[data-test="Summary.Empty"]').exists()).toBe(true);
  });

  it("cuts lines at the template's own breaks, dropping empty ones", () => {
    const lines = toLines(render("a {{ region }}\n\nb", data));
    expect(lines).toHaveLength(2);
  });
});

describe("Summary options", () => {
  it("open a new summary on a sentence made from its result", () => {
    expect(getOptions({}, data).template).toBe("Total revenue is {{ sum(revenue) }} across {{ count() }} rows.");
  });

  it("keep a summary emptied on purpose empty", () => {
    expect(getOptions({ template: "" }, data).template).toBe("");
  });

  it("fall back to a sentence for a layout they do not know", () => {
    expect(getOptions({ layout: "poster" }, data).layout).toBe("sentence");
  });

  it("drop a rule with no column", () => {
    expect(getOptions({ rules: [{ op: ">" }, rules[0]] }, data).rules).toEqual([rules[0]]);
  });
});

describe("Summary editor", () => {
  function editor(options: any, onOptionsChange: any) {
    return mount(
      <Editor
        type="SUMMARY"
        visualizationName="Summary"
        data={data}
        options={getOptions(options, data)}
        onOptionsChange={onOptionsChange}
      />
    );
  }

  it("inserts a column into the text", () => {
    const changed = jest.fn();
    const wrapper = editor({ template: "Top: " }, changed);

    wrapper.find('button[data-test="Summary.Insert.region"]').simulate("click");

    expect(changed.mock.calls[0][0].template).toContain("{{ region }}");
  });

  it("lists what the text asks for that the result cannot answer", () => {
    const wrapper = editor({ template: "{{ revnue }}" }, jest.fn());

    expect(wrapper.find('[data-test="Summary.Problems"]').text()).toContain("did you mean revenue?");
  });

  it("adds a rule and removes one -- replacing the list, so a removed rule stays removed", () => {
    const changed = jest.fn();
    const wrapper = editor({ template: "x", rules: [rules[0]] }, changed);
    wrapper.find(".ant-tabs-tab").at(1).simulate("click");
    wrapper.update();

    wrapper.find('button[data-test="Summary.Rule.Add"]').simulate("click");
    expect(changed.mock.calls[0][0].rules).toHaveLength(2);

    // The editor's default deep merge would put the removed rule back.
    wrapper.find('button[data-test="Summary.Rule.0.Remove"]').simulate("click");
    expect(changed.mock.calls[1][0].rules).toEqual([]);
  });

  it("inserts where the cursor was, not only at the end", () => {
    const changed = jest.fn();
    const wrapper = editor({ template: "Top:  today." }, changed);
    const area = wrapper.find("textarea").first();

    area.simulate("select", { target: { selectionStart: 5 } });
    wrapper.find('button[data-test="Summary.Insert.region"]').simulate("click");

    expect(changed.mock.calls[changed.mock.calls.length - 1][0].template).toBe("Top: {{ region }} today.");
  });
});
