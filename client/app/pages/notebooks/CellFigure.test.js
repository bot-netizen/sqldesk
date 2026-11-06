import React from "react";
import { shallow } from "enzyme";
import CellFigure, { PlotlyFigure } from "./CellFigure";

/*
  A picture a Python cell ended on.

  The claim worth testing here is the one about cost: a PNG draws with no
  chart library at all, and Plotly is imported on demand rather than put in
  the page-load bundle. This fork moved off Plotly to ECharts on purpose, and
  bringing it back as a cost everybody pays would undo that.
*/
describe("a cell's figure", () => {
  it("draws a PNG as an image, with no chart library involved", () => {
    const figure = shallow(<CellFigure figure={{ kind: "png", data: "aGVsbG8=" }} />);

    expect(figure.find("img").prop("src")).toBe("data:image/png;base64,aGVsbG8=");
  });

  it("gives a PNG alternative text rather than leaving it unlabelled", () => {
    const figure = shallow(<CellFigure figure={{ kind: "png", data: "aGVsbG8=" }} />);

    expect(figure.find("img").prop("alt")).toBeTruthy();
  });

  it("hands a Plotly spec to the renderer that loads Plotly on demand", () => {
    const spec = '{"data":[],"layout":{}}';
    const figure = shallow(<CellFigure figure={{ kind: "plotly", spec }} />);

    expect(figure.find(PlotlyFigure).prop("spec")).toBe(spec);
  });

  it("shows nothing at all when there is no figure", () => {
    expect(shallow(<CellFigure figure={null} />).isEmptyRender()).toBe(true);
  });

  it("says so for a kind this version does not know, rather than drawing nothing", () => {
    // A notebook written by a newer version, opened by an older one. Silence
    // would read as "the cell produced nothing", which is a different thing.
    const figure = shallow(<CellFigure figure={{ kind: "vega", spec: "{}" }} />);

    expect(figure.find('[data-test="CellFigureUnknown"]').exists()).toBe(true);
  });
});
