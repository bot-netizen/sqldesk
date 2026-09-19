import { nothingWasRun, shownResultIds } from "./refreshResults";

function widget(resultId) {
  const w = { resultId };
  w.getQueryResult = () => (w.resultId === null ? null : { getId: () => w.resultId });
  return w;
}

describe("telling whether a Refresh ran anything", () => {
  test("the same results back: nothing was run", () => {
    const widgets = [widget(1), widget(2)];
    const before = shownResultIds(widgets);
    expect(nothingWasRun(before, widgets)).toBe(true);
  });

  test("any new result: something was", () => {
    const widgets = [widget(1), widget(2)];
    const before = shownResultIds(widgets);
    widgets[1].resultId = 3;
    expect(nothingWasRun(before, widgets)).toBe(false);
  });

  test("a widget with no result yet says nothing either way", () => {
    const widgets = [widget(null)];
    expect(nothingWasRun(shownResultIds(widgets), widgets)).toBe(false);
  });
});
