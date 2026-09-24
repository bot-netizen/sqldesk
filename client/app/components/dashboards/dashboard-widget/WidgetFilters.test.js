import React from "react";
import { mount } from "enzyme";
import Parameters from "@/components/Parameters";

jest.mock("@/services/auth", () => ({ currentUser: { hasPermission: () => false } }));
jest.mock("@/components/QueryLink", () => () => null);
jest.mock("@/components/visualizations/VisualizationDescription", () => () => null);
jest.mock("@/components/Parameters", () => () => <div data-test="MockParameters" />);

// eslint-disable-next-line global-require
const { VisualizationWidgetHeader } = require("./VisualizationWidget");

const widget = {
  id: 1,
  options: {},
  visualization: { id: 2, description: "", query: { id: 3 } },
  getQuery: () => ({ id: 3, name: "Query", description: "" }),
};

const param = (name) => ({ name, title: name, type: "number" });
const render = (props) => mount(<VisualizationWidgetHeader widget={widget} {...props} />);
const inline = (w) => w.find('[data-test="WidgetFilters"]').length > 0;

/*
  A widget's own filter belongs to that widget, so it stays visible -- but it
  used to take a 63px block out of a widget that is mostly chart. On the
  title's row it takes the room the title was leaving empty.
*/

describe("where a widget's own filters go", () => {
  test("on the title's row", () => {
    const w = render({ parameters: [param("region")] });
    expect(inline(w)).toBe(true);
    expect(w.find(".t-header-filtered").length).toBeGreaterThan(0);
    expect(w.find(Parameters).length).toBe(1);
  });

  test("and nowhere at all when the widget has none", () => {
    const w = render({ parameters: [] });
    expect(inline(w)).toBe(false);
    expect(w.find(Parameters).length).toBe(0);
  });

  test("back to a block while the layout is being edited", () => {
    // There they are dragged into order, and drag handles want the room.
    const w = render({ parameters: [param("region")], isEditing: true });
    expect(inline(w)).toBe(false);
    expect(w.find(".t-header-filtered").length).toBe(0);
    expect(w.find(Parameters).props().sortable).toBe(true);
  });

  test("the row is drawn once, not once per place it could go", () => {
    expect(render({ parameters: [param("a"), param("b")] }).find(Parameters).length).toBe(1);
  });
});
