import React from "react";
import enzyme from "enzyme";

import Column from "./number";

function findByTestID(wrapper: any, testId: any) {
  return wrapper.find(`[data-test="${testId}"]`);
}

function mount(column: any, done: any) {
  return enzyme.mount(
    <Column.Editor
      // @ts-expect-error ts-migrate(2322) FIXME: Type '{ visualizationName: string; column: any; on... Remove this comment to see the full error message
      visualizationName="Test"
      column={column}
      onChange={(changedColumn) => {
        expect(changedColumn).toMatchSnapshot();
        done();
      }}
    />
  );
}

describe("Visualizations -> Table -> Columns -> Number", () => {
  describe("Editor", () => {
    test("Changes format", (done) => {
      // The numeral format string became a set of controls, and a change now
      // sends up the whole shared format -- read out of whatever the column
      // was holding, which for an existing one is the string.
      const el = mount(
        {
          name: "a",
          numberFormat: "0[.]0000",
        },
        done
      );

      findByTestID(el, "Table.ColumnEditor.Number.Format.Suffix")
        .last()
        .find("input")
        .simulate("change", { target: { value: "%" } });
    });

    test("opens on what a saved column already says", () => {
      const el = enzyme.mount(
        // @ts-expect-error the editor takes more props than this test gives it
        <Column.Editor visualizationName="Test" column={{ name: "a", numberFormat: "0,0.00" }} onChange={() => {}} />
      );

      expect(findByTestID(el, "Table.ColumnEditor.Number.Format.Decimals").last().find("input").prop("value")).toBe(
        "2"
      );
    });
  });
});
