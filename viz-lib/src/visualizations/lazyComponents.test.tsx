import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";
import registeredVisualizations from "./registeredVisualizations";
import lazyVisualizationComponent from "./lazyComponents";

/*
  Visualizations are fetched on demand, which means every one of them now
  arrives through Suspense. Two things about that are worth pinning down:

  - the fallback gives way to the real thing once the module lands, and
  - asking for the same visualization twice gives back the *same* component.

  The second is the subtle one. React identifies a component by its reference,
  so a freshly made React.lazy on each render is a different component type --
  React would unmount the old subtree and mount a new one, and a table would
  lose its page, a chart its zoom, every time an unrelated prop changed on the
  parent. Nothing about the screen would look wrong in a screenshot.

  Stub visualizations rather than real ones: jest cannot require ECharts, and
  what is under test is the loading, not any particular chart.
*/

let mounts = 0;

function StubRenderer({ label }: { label?: string }) {
  React.useEffect(() => {
    mounts += 1;
  }, []);
  return <div className="stub">{label || "drawn"}</div>;
}

function stubVisualization(type: string) {
  let release: (components: any) => void = () => {};
  const pending = new Promise<any>((resolve) => {
    release = resolve;
  });
  (registeredVisualizations as any)[type] = {
    type,
    name: type,
    getOptions: (o: any) => o || {},
    load: () => pending,
  };
  return { release: () => release({ Renderer: StubRenderer, Editor: StubRenderer }) };
}

function mount(element: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => {
    ReactDOM.render(element, container);
  });
  return {
    container,
    rerender(next: React.ReactElement) {
      act(() => {
        ReactDOM.render(next, container);
      });
    },
    unmount() {
      act(() => {
        ReactDOM.unmountComponentAtNode(container);
      });
      container.remove();
    },
  };
}

/**
 * Wait for React to re-render with the resolved module.
 *
 * Polled rather than a fixed delay: React schedules its retry after the lazy
 * payload resolves, so how many turns of the loop that takes depends on how
 * busy the machine is -- a single flush passes alone and fails in a full suite
 * run, which is the worst kind of test.
 */
async function waitFor(done: () => boolean, what: string) {
  for (let i = 0; i < 100; i += 1) {
    if (done()) {
      return;
    }
    // eslint-disable-next-line no-await-in-loop
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1));
    });
  }
  throw new Error(`timed out waiting for ${what}`);
}

beforeEach(() => {
  mounts = 0;
});

describe("lazyVisualizationComponent", () => {
  test("shows the fallback until the module lands, then the visualization", async () => {
    const type = "STUB_ONE";
    const stub = stubVisualization(type);
    const Lazy = lazyVisualizationComponent(type, "Renderer");

    const view = mount(
      <React.Suspense fallback={<div className="waiting" />}>
        <Lazy />
      </React.Suspense>
    );
    expect(view.container.querySelector(".waiting")).not.toBeNull();
    expect(view.container.querySelector(".stub")).toBeNull();

    stub.release();
    await waitFor(() => !!view.container.querySelector(".stub"), "the visualization to be drawn");

    expect(view.container.querySelector(".waiting")).toBeNull();
    expect(view.container.querySelector(".stub")!.textContent).toBe("drawn");

    view.unmount();
    delete (registeredVisualizations as any)[type];
  });

  test("gives back the same component every time, so nothing remounts", async () => {
    const type = "STUB_TWO";
    const stub = stubVisualization(type);
    expect(lazyVisualizationComponent(type, "Renderer")).toBe(lazyVisualizationComponent(type, "Renderer"));
    // The Renderer and the Editor are different components of the same module.
    expect(lazyVisualizationComponent(type, "Renderer")).not.toBe(lazyVisualizationComponent(type, "Editor"));

    function Host({ label }: { label: string }) {
      const Lazy = lazyVisualizationComponent(type, "Renderer");
      return (
        <React.Suspense fallback={<div className="waiting" />}>
          <Lazy label={label} />
        </React.Suspense>
      );
    }

    const view = mount(<Host label="first" />);
    stub.release();
    await waitFor(() => !!view.container.querySelector(".stub"), "the visualization to be drawn");
    expect(mounts).toBe(1);

    // A re-render for an unrelated reason: the visualization is updated in
    // place, not thrown away and rebuilt.
    view.rerender(<Host label="second" />);
    await waitFor(() => view.container.querySelector(".stub")?.textContent === "second", "the new label to be shown");
    expect(mounts).toBe(1);

    view.unmount();
    delete (registeredVisualizations as any)[type];
  });

  test("a visualization with no Editor renders nothing rather than crashing", async () => {
    const type = "STUB_THREE";
    (registeredVisualizations as any)[type] = {
      type,
      name: type,
      getOptions: (o: any) => o || {},
      load: () => Promise.resolve({ Renderer: StubRenderer }),
    };
    const Lazy = lazyVisualizationComponent(type, "Editor");

    const view = mount(
      <React.Suspense fallback={<div className="waiting" />}>
        <Lazy />
      </React.Suspense>
    );
    await waitFor(() => !view.container.querySelector(".waiting"), "the empty editor to replace the fallback");

    expect(view.container.innerHTML).toBe("");

    view.unmount();
    delete (registeredVisualizations as any)[type];
  });
});
