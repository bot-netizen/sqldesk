import React from "react";
import enzyme from "enzyme";
import Editor from "./Editor";

/*
  The visualization dialog takes whatever the editor hands back as the whole
  of the options. An editor that sends only what changed wipes everything
  else -- choose a palette and the percentages go.
*/
const data = {
  columns: [{ name: "value" }, { name: "stage1" }, { name: "stage2" }],
  rows: [
    { stage1: "Bid requests", stage2: "Bid passes", value: 900 },
    { stage1: "Bid requests", stage2: "Bid chosen", value: 100 },
  ],
};

function mount(options: any) {
  const onOptionsChange = jest.fn();
  const wrapper = enzyme.mount(<Editor options={options} data={data} onOptionsChange={onOptionsChange} />);
  return { wrapper, onOptionsChange };
}

function control(wrapper: any, test: string) {
  return wrapper.find(`[data-test="${test}"]`).first();
}

describe("the sankey editor", () => {
  test("keeps every other setting when one changes", () => {
    const { wrapper, onOptionsChange } = mount({ showNodeValues: true, nodePercent: "total" });

    control(wrapper, "Sankey.ColorScheme").prop("onChange")("Tableau 10");

    expect(onOptionsChange).toHaveBeenCalledWith(
      expect.objectContaining({ showNodeValues: true, nodePercent: "total", colorScheme: "Tableau 10" })
    );
  });

  test("offers every label to leave out", () => {
    const { wrapper } = mount({});
    // antd draws the options only once the list is open; they are its children.
    const offered = React.Children.map(
      control(wrapper, "Sankey.HiddenNodes").prop("children"),
      (option: any) => option.props.value
    );

    expect(offered).toEqual(expect.arrayContaining(["Bid requests", "Bid passes", "Bid chosen"]));
  });

  test("replaces the list left out rather than merging into it", () => {
    const { wrapper, onOptionsChange } = mount({ hiddenNodes: ["Bid passes", "Bid chosen"] });

    control(wrapper, "Sankey.HiddenNodes").prop("onChange")(["Bid chosen"]);

    expect(onOptionsChange.mock.calls[0][0].hiddenNodes).toEqual(["Bid chosen"]);
  });

  test("lists a colour for each label, and only the first stage's for journeys", () => {
    expect(mount({}).wrapper.find(".sankey-editor-colour")).toHaveLength(4);
    expect(mount({ linkColor: "journey" }).wrapper.find(".sankey-editor-colour")).toHaveLength(1);
  });

  test("a colour chosen for one label keeps the others chosen", () => {
    const { wrapper, onOptionsChange } = mount({ nodeColors: { "Bid passes": "#111111" } });

    const picker: any = wrapper.find(".sankey-editor-colour").at(0).find("ColorPicker").first();
    picker.prop("onChange")("#222222");

    expect(onOptionsChange.mock.calls[0][0].nodeColors).toEqual({ "Bid passes": "#111111", "Bid requests": "#222222" });
  });
});
