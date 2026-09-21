import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";

import useEditModeHandler, { DashboardStatusEnum } from "./useEditModeHandler";

/*
  Dragging or resizing a widget used to be written to the server about two
  seconds later, whatever you did next. So a dashboard was changed by opening
  it and nudging something -- Done Editing never had to be pressed, and there
  was no way back.

  Now the arrangement is held until it is saved on purpose. Which means the
  thing to be careful about has moved: nothing may be written before Done
  Editing, and nothing may be lost without someone saying so.
*/

jest.mock("@/services/location", () => ({
  __esModule: true,
  default: { search: {}, setSearch: () => {} },
}));

jest.mock("@/services/notification", () => ({
  __esModule: true,
  default: { error: jest.fn() },
}));

function fakeWidget(id, position) {
  return {
    id,
    options: { position },
    save: jest.fn(function save(_key, changes) {
      // The real one writes and then holds the new value.
      this.options.position = changes.position;
      return Promise.resolve(this);
    }),
  };
}

const AT_ORIGIN = { col: 0, row: 0, sizeX: 6, sizeY: 6, autoHeight: false };
const MOVED = { col: 6, row: 0, sizeX: 6, sizeY: 6, autoHeight: false };

function render(widgets, canEdit = true) {
  const handler = { current: null };
  function Probe({ widgets: w }) {
    handler.current = useEditModeHandler(canEdit, w);
    return null;
  }
  const container = document.createElement("div");
  const mount = (w) =>
    act(() => {
      ReactDOM.render(<Probe widgets={w} />, container);
    });
  mount(widgets);
  return {
    handler,
    rerender: mount,
    unmount: () => act(() => ReactDOM.unmountComponentAtNode(container)),
  };
}

/** Report a layout the way the grid does, keyed by widget id. */
function layout(widgets, positions) {
  const reported = {};
  widgets.forEach((widget, index) => {
    reported[widget.id] = positions[index];
  });
  return reported;
}

describe("editing a dashboard's layout", () => {
  test("moving a widget writes nothing", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));

    expect(widget.save).not.toHaveBeenCalled();
  });

  test("moving a widget says there is something unsaved", () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));

    expect(handler.current.hasUnsavedChanges).toBe(true);
    expect(handler.current.dashboardStatus).toBe(DashboardStatusEnum.UNSAVED);
  });

  test("the grid reporting the layout it already had is not a change", () => {
    // The grid reports its layout on mount, and on every reflow. If that
    // counted, merely opening a dashboard would offer to save it.
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [{ ...AT_ORIGIN }])));

    expect(handler.current.hasUnsavedChanges).toBe(false);
    expect(handler.current.dashboardStatus).toBe(DashboardStatusEnum.SAVED);
  });

  test("moving a widget back again leaves nothing to save", () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    act(() => handler.current.updateDashboardLayout(layout([widget], [{ ...AT_ORIGIN }])));

    expect(handler.current.hasUnsavedChanges).toBe(false);
  });

  test("saving writes the widgets that moved, and only those", async () => {
    const moved = fakeWidget(1, { ...AT_ORIGIN });
    const stayed = fakeWidget(2, { ...MOVED });
    const widgets = [moved, stayed];
    const { handler } = render(widgets);

    act(() => handler.current.updateDashboardLayout(layout(widgets, [MOVED, { ...MOVED }])));
    await act(async () => {
      await handler.current.saveDashboardLayout();
    });

    expect(moved.save).toHaveBeenCalledWith("options", { position: MOVED });
    expect(stayed.save).not.toHaveBeenCalled();
  });

  test("saving says so, and then says there is nothing left", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    await act(async () => {
      const saved = await handler.current.saveDashboardLayout();
      expect(saved).toBe(true);
    });

    expect(handler.current.hasUnsavedChanges).toBe(false);
    expect(handler.current.dashboardStatus).toBe(DashboardStatusEnum.SAVED);
  });

  test("saving with nothing moved writes nothing", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    await act(async () => {
      const saved = await handler.current.saveDashboardLayout();
      expect(saved).toBe(true);
    });

    expect(widget.save).not.toHaveBeenCalled();
  });

  test("a failed save keeps the changes and says it failed", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    widget.save = jest.fn(() => Promise.reject(new Error("no")));
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    await act(async () => {
      const saved = await handler.current.saveDashboardLayout();
      expect(saved).toBe(false);
    });

    // Still unsaved, so the caller knows not to leave: the arrangement exists
    // nowhere but here.
    expect(handler.current.hasUnsavedChanges).toBe(true);
    expect(handler.current.dashboardStatus).toBe(DashboardStatusEnum.SAVING_FAILED);
  });

  test("a failed save is not talked over by the next drag", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    widget.save = jest.fn(() => Promise.reject(new Error("no")));
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    await act(async () => {
      await handler.current.saveDashboardLayout();
    });
    act(() => handler.current.updateDashboardLayout(layout([widget], [{ ...MOVED, row: 3 }])));

    expect(handler.current.dashboardStatus).toBe(DashboardStatusEnum.SAVING_FAILED);
  });

  test("discarding writes nothing and leaves nothing unsaved", () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    act(() => handler.current.discardDashboardLayout());

    expect(widget.save).not.toHaveBeenCalled();
    expect(handler.current.hasUnsavedChanges).toBe(false);
    expect(widget.options.position).toEqual(AT_ORIGIN);
  });

  test("discarding tells the grid to build itself again", () => {
    // The widgets still hold the stored positions, so that is all it takes.
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);
    const before = handler.current.layoutGeneration;

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    act(() => handler.current.discardDashboardLayout());

    expect(handler.current.layoutGeneration).not.toBe(before);
  });

  test("saving after discarding writes nothing", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget]);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    act(() => handler.current.discardDashboardLayout());
    await act(async () => {
      await handler.current.saveDashboardLayout();
    });

    expect(widget.save).not.toHaveBeenCalled();
  });

  test("a widget deleted while editing is not saved, and does not throw", async () => {
    const kept = fakeWidget(1, { ...AT_ORIGIN });
    const removed = fakeWidget(2, { ...AT_ORIGIN });
    const { handler, rerender } = render([kept, removed]);

    act(() => handler.current.updateDashboardLayout(layout([kept, removed], [MOVED, MOVED])));
    rerender([kept]);

    await act(async () => {
      await handler.current.saveDashboardLayout();
    });

    expect(kept.save).toHaveBeenCalled();
    expect(removed.save).not.toHaveBeenCalled();
  });

  test("someone who cannot edit never writes", async () => {
    const widget = fakeWidget(1, { ...AT_ORIGIN });
    const { handler } = render([widget], false);

    act(() => handler.current.updateDashboardLayout(layout([widget], [MOVED])));
    await act(async () => {
      await handler.current.saveDashboardLayout();
    });

    expect(widget.save).not.toHaveBeenCalled();
    expect(handler.current.editingLayout).toBe(false);
  });
});
