import React from "react";
import { shallow } from "enzyme";
import StreamMarker, { StreamRollup, detail, rate } from "./StreamMarker";
import { rollUp, streamsFor } from "../hooks/useRunningStreams";

jest.mock(
  "@/components/Tooltip",
  () =>
    ({ children }) =>
      children
);

/*
  What a streaming panel says about itself, and what the board says when its
  panels disagree.

  The mismatch being fixed is structural: the refresh is per dashboard and the
  events are per widget, so "● Live · every 2 seconds" describes the redraw and
  nothing about whether any data is arriving. A chart that stopped twenty
  minutes ago looks exactly like one keeping up.
*/
function aStream(extras = {}) {
  return {
    id: 1,
    topic: "orders",
    table: "orders",
    data_source_id: 3,
    state: "running",
    observed_rate: 1234,
    sampled: false,
    sample_rate: 1,
    describes: "about 4 minutes of history",
    watchers: 2,
    ...extras,
  };
}

describe("a panel's own marker", () => {
  it("is nothing at all on a panel with no stream, which is most panels", () => {
    expect(shallow(<StreamMarker stream={null} />).isEmptyRender()).toBe(true);
  });

  it("shows the rate while it is consuming", () => {
    const marker = shallow(<StreamMarker stream={aStream()} />);

    expect(marker.find(".stream-marker-label").text()).toBe("1234/s");
  });

  it("says paused when it is not consuming, which is otherwise invisible", () => {
    const marker = shallow(<StreamMarker stream={aStream({ state: "paused" })} />);

    expect(marker.find(".stream-marker-label").text()).toBe("paused");
    expect(marker.find(".stream-marker").hasClass("stream-marker-paused")).toBe(true);
  });

  it("says sampled loudest of all, because the number is then an estimate", () => {
    const marker = shallow(<StreamMarker stream={aStream({ sampled: true, sample_rate: 10 })} />);

    expect(marker.find(".stream-marker-label").text()).toBe("1 in 10");
    expect(marker.find(".stream-marker").hasClass("stream-marker-sampled")).toBe(true);
  });

  it("tells a screen reader what sampling means rather than only colouring it", () => {
    const marker = shallow(<StreamMarker stream={aStream({ sampled: true, sample_rate: 10 })} />);

    expect(marker.find(".sr-only").text()).toContain("estimates");
  });
});

describe("what the hover says", () => {
  it("names the topic, the rate and the window", () => {
    const said = detail(aStream());

    expect(said).toContain("orders");
    expect(said).toContain("events a second");
    expect(said).toContain("about 4 minutes of history");
  });

  it("spells out what sampling costs", () => {
    expect(detail(aStream({ sampled: true, sample_rate: 10 }))).toContain("estimates");
  });

  it("carries the reason a stream stopped", () => {
    expect(detail(aStream({ state: "paused", last_error: "topic does not exist" }))).toContain("topic does not exist");
  });
});

describe("a rate a person can read", () => {
  it("rounds away false precision", () => {
    // The server divides events by a window, so a quiet topic arrives as
    // 0.8166666666666667 -- seventeen digits in a chip this size.
    expect(rate(0.8166666666666667)).toBe("0.82");
    expect(rate(12.345)).toBe("12.3");
    expect(rate(1234.5)).toBe("1235");
    expect(rate(45000)).toBe("45k");
    expect(rate(0)).toBe("0");
  });
});

describe("the board's roll-up", () => {
  it("is nothing when the board has no streams", () => {
    expect(rollUp([])).toBeNull();
  });

  it("says the simple thing when they all agree", () => {
    expect(rollUp([aStream(), aStream({ id: 2 })]).state).toBe("2 streams consuming");
  });

  it("says how many when they do not, which is the whole point of it", () => {
    const summary = rollUp([aStream(), aStream({ id: 2, state: "paused" }), aStream({ id: 3 })]);

    expect(summary.state).toBe("2 of 3 streams consuming");
    expect(summary.everything).toBe(false);
  });

  it("does not say two of two when none is consuming", () => {
    expect(rollUp([aStream({ state: "paused" }), aStream({ id: 2, state: "paused" })]).state).toBe(
      "no streams consuming of 2"
    );
  });

  it("calls out sampling separately, because it is a different kind of wrong", () => {
    const summary = rollUp([aStream({ sampled: true }), aStream({ id: 2 })]);

    expect(summary.state).toBe("2 streams consuming");
    expect(summary.sampling).toBe("1 sampled");
    expect(summary.everything).toBe(false);
  });

  it("renders the partial case so it reads as a warning", () => {
    const badge = shallow(<StreamRollup summary={rollUp([aStream(), aStream({ id: 2, state: "paused" })])} />);

    expect(badge.find(".stream-rollup").hasClass("stream-rollup-partial")).toBe(true);
  });

  it("renders nothing with no summary, so an ordinary dashboard is untouched", () => {
    expect(shallow(<StreamRollup summary={null} />).isEmptyRender()).toBe(true);
  });
});

describe("which stream a panel is drawn from", () => {
  const streams = [aStream(), aStream({ id: 2, topic: "payments", table: "payments" })];

  it("matches the topic's table named in the query", () => {
    const found = streamsFor({ query: "SELECT * FROM orders", data_source_id: 3 }, streams);

    expect(found.map((one) => one.topic)).toEqual(["orders"]);
  });

  it("does not match a table whose name merely contains it", () => {
    expect(streamsFor({ query: "SELECT * FROM orders_archive", data_source_id: 3 }, streams)).toEqual([]);
  });

  it("does not match the same name on another cluster", () => {
    expect(streamsFor({ query: "SELECT * FROM orders", data_source_id: 9 }, streams)).toEqual([]);
  });

  it("finds both when a query joins two topics", () => {
    const found = streamsFor({ query: "SELECT * FROM orders JOIN payments USING (id)", data_source_id: 3 }, streams);

    expect(found).toHaveLength(2);
  });

  it("is nothing for a query with no text, rather than everything", () => {
    expect(streamsFor({ data_source_id: 3 }, streams)).toEqual([]);
    expect(streamsFor(null, streams)).toEqual([]);
  });
});
