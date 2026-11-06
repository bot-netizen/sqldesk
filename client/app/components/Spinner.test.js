import React from "react";
import { mount } from "enzyme";

import Spinner from "@/components/Spinner";
import LoadingState from "@/components/items-list/components/LoadingState";

/*
  The spinner is drawn by CSS, so what a test can hold onto is the contract the
  stylesheet depends on: the class that carries the animation, the size
  modifier, and that it is hidden from a screen reader rather than read out as
  a stray element beside the words that already say what is happening.
*/
describe("Spinner", () => {
  test("carries the class the animation is attached to", () => {
    const wrapper = mount(<Spinner />);
    expect(wrapper.find("span").hasClass("sqldesk-spinner")).toBe(true);
  });

  test("follows the surrounding text size unless told otherwise", () => {
    expect(
      mount(<Spinner />)
        .find("span")
        .hasClass("sqldesk-spinner-inline")
    ).toBe(true);
    expect(
      mount(<Spinner size="large" />)
        .find("span")
        .hasClass("sqldesk-spinner-large")
    ).toBe(true);
  });

  test("keeps a caller's own classes, which position it", () => {
    const wrapper = mount(<Spinner className="m-r-5" />);
    expect(wrapper.find("span").hasClass("m-r-5")).toBe(true);
    expect(wrapper.find("span").hasClass("sqldesk-spinner")).toBe(true);
  });

  // It is never the only thing announced: every caller wraps it in a live
  // region whose text says what is loading.
  test("is not read out on its own", () => {
    expect(
      mount(<Spinner />)
        .find("span")
        .prop("aria-hidden")
    ).toBe("true");
  });
});

describe("LoadingState", () => {
  test("draws the spinner and says what is happening", () => {
    const wrapper = mount(<LoadingState />);
    expect(wrapper.find(Spinner)).toHaveLength(1);
    expect(wrapper.text()).toContain("Loading...");
    expect(wrapper.find('[role="status"]').exists()).toBe(true);
  });

  // Most list pages drop it straight onto the page background, so the tile is
  // the default and the pages that already have one pass className="".
  test("comes as a tile unless a caller says otherwise", () => {
    const box = mount(<LoadingState />)
      .find(".big-message")
      .first();
    expect(box.hasClass("tiled")).toBe(true);
    expect(box.hasClass("bg-white")).toBe(true);
  });

  test("an empty className replaces the default rather than adding to it", () => {
    const wrapper = mount(<LoadingState className="" />);
    expect(wrapper.find(".big-message").first().hasClass("tiled")).toBe(false);
  });
});
