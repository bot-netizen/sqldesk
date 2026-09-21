import React from "react";
import { mount } from "enzyme";
import Dropdown from "antd/lib/dropdown";
import { FilterControl, ColumnsControl, visibleColumns } from "./ListPageControls";

// Both controls hang their contents off a Dropdown overlay, which antd only
// mounts once the trigger is clicked. Rendering the overlay directly tests what
// it contains without driving the popup open.
function getOverlay(wrapper) {
  return mount(wrapper.find(Dropdown).prop("overlay"));
}

const COLUMNS = [
  { title: "" }, // the favourites star
  { title: "Name" },
  { title: "Owner" },
  { title: "Created" },
  { title: undefined }, // the row actions
];

describe("ColumnsControl", () => {
  it("lists every column that has a title", () => {
    const labels = getOverlay(mount(<ColumnsControl columns={COLUMNS} hidden={[]} onToggle={() => {}} />))
      .find("label")
      .map((l) => l.text().trim());

    expect(labels).toEqual(["Name", "Owner", "Created"]);
  });

  it("keeps a hidden column in the menu, unticked", () => {
    // The whole point of the menu: hiding a column used to remove it from here
    // as well, leaving nothing to tick to bring it back.
    const overlay = getOverlay(mount(<ColumnsControl columns={COLUMNS} hidden={["Owner"]} onToggle={() => {}} />));

    const owner = overlay.find("label").filterWhere((l) => l.text().trim() === "Owner");
    expect(owner).toHaveLength(1);
    expect(owner.find("input").prop("checked")).toBe(false);
  });

  it("reports the column that was toggled", () => {
    const onToggle = jest.fn();
    const overlay = getOverlay(mount(<ColumnsControl columns={COLUMNS} hidden={[]} onToggle={onToggle} />));

    overlay
      .find("label")
      .filterWhere((l) => l.text().trim() === "Created")
      .find("input")
      .simulate("change");

    expect(onToggle).toHaveBeenCalledWith("Created");
  });

  it("leaves structural columns out", () => {
    // A column with no title is the favourites star or the row actions, which
    // are not the user's to hide.
    const overlay = getOverlay(mount(<ColumnsControl columns={COLUMNS} hidden={[]} onToggle={() => {}} />));

    expect(overlay.find("label")).toHaveLength(3);
  });
});

describe("visibleColumns", () => {
  it("drops the hidden ones", () => {
    expect(visibleColumns(COLUMNS, ["Owner"]).map((c) => c.title)).toEqual(["", "Name", "Created", undefined]);
  });

  it("never drops a structural column", () => {
    // Their titles are "" or undefined, which must not be matched against the
    // hidden list -- losing the row actions would take the menu with it.
    expect(visibleColumns(COLUMNS, ["", undefined]).map((c) => c.title)).toEqual([
      "",
      "Name",
      "Owner",
      "Created",
      undefined,
    ]);
  });

  it("returns everything when nothing is hidden", () => {
    expect(visibleColumns(COLUMNS, [])).toHaveLength(COLUMNS.length);
  });
});

describe("FilterControl", () => {
  it("does not let a click on the field reach the dropdown", () => {
    // antd closes a Dropdown when its overlay is clicked, which for a panel
    // built around a text field meant the field vanished as you tried to type.
    const overlay = getOverlay(mount(<FilterControl value="" onChange={() => {}} />));

    const event = { stopPropagation: jest.fn() };
    overlay.find(".list-page-filter-panel").first().simulate("click", event);

    expect(event.stopPropagation).toHaveBeenCalled();
  });

  it("reports what was typed", () => {
    const onChange = jest.fn();
    const overlay = getOverlay(mount(<FilterControl value="" onChange={onChange} />));

    overlay
      .find("input")
      .first()
      .simulate("change", { target: { value: "revenue" } });

    expect(onChange).toHaveBeenCalledWith("revenue");
  });

  /*
    The list debounces its search term by 200ms, so `value` is always a little
    behind what has been typed. While the field took its value straight from
    that prop, each keystroke was replaced by the older term and then
    reappeared: typing at any speed dropped characters and the word in
    progress vanished as you wrote it.

    These drive the real popup rather than mounting the overlay element on its
    own -- a detached copy has none of the component's state, which is exactly
    what is being tested.
  */
  function openFilter(wrapper) {
    wrapper.find('button[data-test="ListFilterButton"]').simulate("click");
    wrapper.update();
    return wrapper;
  }

  const field = (wrapper) => wrapper.find("input").first();

  function type(wrapper, text) {
    field(wrapper).simulate("change", { target: { value: text } });
    wrapper.update();
  }

  it("keeps what was typed before the list has caught up", () => {
    const wrapper = openFilter(mount(<FilterControl value="" onChange={() => {}} />));

    type(wrapper, "rev");

    expect(field(wrapper).prop("value")).toBe("rev");
  });

  it("keeps a whole word typed faster than the list updates", () => {
    const wrapper = openFilter(mount(<FilterControl value="" onChange={() => {}} />));

    // `value` never moves: the debounce has not fired for any of these.
    "revenue".split("").reduce((sofar, letter) => {
      const next = sofar + letter;
      type(wrapper, next);
      return next;
    }, "");

    expect(field(wrapper).prop("value")).toBe("revenue");
  });

  it("does not undo typing when the list echoes an earlier term back", () => {
    // A slow request can land an older term after a newer one. Whoever is
    // typing must not have the field rewritten under the cursor.
    const wrapper = openFilter(mount(<FilterControl value="" onChange={() => {}} />));
    field(wrapper).simulate("focus");
    type(wrapper, "revenue");

    wrapper.setProps({ value: "rev" });
    wrapper.update();

    expect(field(wrapper).prop("value")).toBe("revenue");
  });

  it("follows the term when it is changed somewhere else", () => {
    // The back button, or a search cleared while this panel was closed.
    const wrapper = openFilter(mount(<FilterControl value="revenue" onChange={() => {}} />));
    field(wrapper).simulate("blur");
    expect(field(wrapper).prop("value")).toBe("revenue");

    wrapper.setProps({ value: "" });
    wrapper.update();

    expect(field(wrapper).prop("value")).toBe("");
  });
});
