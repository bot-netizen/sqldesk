import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";

import { SHAPES } from "./dataShapes";
import { VARIANTS } from "./optionVariants";

import tableOptions from "../table/getOptions";
import TableRenderer from "../table/Renderer";
import detailsOptions from "../details/getOptions";
import DetailsRenderer from "../details/Renderer";
import statusGridOptions from "../status-grid/getOptions";
import StatusGridRenderer from "../status-grid/Renderer";
import funnelConfig from "../funnel";

// The funnel's drawn shape reaches ECharts, which jest cannot load, and it is
// not what is under test here -- only the bars, which are the default and the
// only variants this file keeps.
jest.mock("../funnel/Renderer/DrawnFunnel", () => ({
  __esModule: true,
  default: () => null,
}));
// eslint-disable-next-line @typescript-eslint/no-var-requires
const FunnelRenderer = require("../funnel/Renderer").default;

/*
  The visualizations that draw with the DOM rather than with ECharts, mounted
  for real against every option and every awkward result.

  These fail differently from the chart ones: not a blank canvas but a throw
  during render, which the error boundary turns into "Error while rendering
  visualization" across the whole widget. A column of nulls or a row count of
  zero is all it takes, and every one of these predates the shared option
  layer, so none of them was written with the others' edge cases in mind.

  Five are absent on purpose, each for a reason that is about the test
  environment rather than about them: the counter reaches ECharts through its
  sparkline, the word cloud's layout does pixel collision detection against a
  canvas jsdom does not have, and the pivot table and the two maps wrap
  libraries that want a real layout engine. All five are covered by the option
  matrix, and by the pass over a running instance.
*/

interface Subject {
  name: string;
  type: string;
  Renderer: any;
  getOptions: (options: any, data: any) => any;
}

const SUBJECTS: Subject[] = [
  { name: "Table", type: "TABLE", Renderer: TableRenderer, getOptions: tableOptions },
  { name: "Details", type: "DETAILS", Renderer: DetailsRenderer, getOptions: detailsOptions },
  { name: "Status grid", type: "STATUS_GRID", Renderer: StatusGridRenderer, getOptions: statusGridOptions },
  {
    name: "Funnel",
    type: "FUNNEL",
    Renderer: FunnelRenderer,
    getOptions: (o, d) => (funnelConfig as any).getOptions(o, d),
  },
];

function mount(element: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => {
    ReactDOM.render(element, container);
  });
  return {
    container,
    unmount() {
      act(() => {
        ReactDOM.unmountComponentAtNode(container);
      });
      container.remove();
    },
  };
}

describe("every DOM visualization, mounted", () => {
  SUBJECTS.forEach((subject) => {
    // The drawn funnel goes through ECharts, so only the bars are mounted here.
    const variants = (VARIANTS[subject.type] || [{ name: "defaults", options: {} }]).filter(
      (v) => v.options.shape !== "funnel"
    );

    describe(subject.name, () => {
      test.each(SHAPES.map((s) => [s.name, s] as const))("renders %s", (_n, shape) => {
        const data = { columns: shape.columns, rows: shape.rows };
        variants.forEach((variant) => {
          const options = subject.getOptions(variant.options, data);
          const view = mount(<subject.Renderer data={data} options={options} visualizationName={subject.name} />);
          try {
            // Mounting without throwing is most of it; a renderer that bails
            // out to null is a legitimate answer for an empty result.
            expect(view.container).toBeDefined();
          } finally {
            view.unmount();
          }
        });
      });

      test("survives its data being replaced underneath it", () => {
        // A dashboard refresh swaps the result on a mounted component, which
        // is not the same code path as a first render -- table state and
        // memoised columns have both broken here before.
        const first = SHAPES[0];
        const view = mount(
          <subject.Renderer
            data={{ columns: first.columns, rows: first.rows }}
            options={subject.getOptions(variants[0].options, { columns: first.columns, rows: first.rows })}
            visualizationName={subject.name}
          />
        );
        try {
          SHAPES.slice(1).forEach((shape) => {
            const data = { columns: shape.columns, rows: shape.rows };
            const options = subject.getOptions(variants[0].options, data);
            expect(() => {
              act(() => {
                ReactDOM.render(
                  <subject.Renderer data={data} options={options} visualizationName={subject.name} />,
                  view.container
                );
              });
            }).not.toThrow();
          });
        } finally {
          view.unmount();
        }
      });
    });
  });
});
