import React, { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { filter, find } from "lodash";

import { axios } from "@/services/axios";

/*
  What each panel's topic is doing, asked once for the whole dashboard.

  The mismatch this exists to fix is structural: **the refresh is per
  dashboard, the events are per widget.** One board can hold widgets over three
  topics, each arriving at its own rate, any one of which can be paused,
  sampled or empty while the other two are fine -- and a single "Live · every 2
  seconds" badge on the header describes the redraw, not the data. A chart that
  stopped moving twenty minutes ago looks exactly like one that is keeping up.

  One request, not one per widget. The answer is the same for every panel on
  the page, and a board of eight widgets polling separately would be eight
  requests every few seconds for one list.

  Asked only while the dashboard is live. A streaming dashboard that is not
  running has nothing to report, and a timer for it would be a request per
  viewer per tab for an answer that cannot change.
*/
const EVERY_MS = 5000;

export const StreamsContext = React.createContext(null);

/**
 * Which running stream a widget is drawn from, or null.
 *
 * Matched the way the stream editor matches: the topic's table name appearing
 * as a word in the query, on the same data source. A query joining two topics
 * belongs to both, and the first is the one shown -- a panel's corner has room
 * for one state, and "consuming" beside "paused" would be a question rather
 * than an answer.
 */
export function streamsFor(query, streams) {
  if (!query || !query.query) {
    return [];
  }
  return filter(streams, (stream) => {
    if (query.data_source_id && stream.data_source_id !== query.data_source_id) {
      return false;
    }
    return new RegExp(`\\b${stream.table}\\b`, "i").test(query.query);
  });
}

/**
 * The one line a dashboard's header can say about topics that disagree.
 *
 * "3 streams consuming" when they agree, "2 of 3 streams consuming" when they
 * do not -- and sampling called out separately, because a sampled stream is
 * the case where the number on the chart is an estimate and silence about it
 * is the worst outcome.
 */
export function rollUp(streams) {
  if (!streams || streams.length === 0) {
    return null;
  }
  const consuming = filter(streams, { state: "running" }).length;
  const sampled = filter(streams, "sampled").length;
  const total = streams.length;
  const word = total === 1 ? "stream" : "streams";
  let state;
  if (consuming === total) {
    state = `${total} ${word} consuming`;
  } else if (consuming === 0) {
    state = total === 1 ? "stream paused" : `no streams consuming of ${total}`;
  } else {
    state = `${consuming} of ${total} ${word} consuming`;
  }
  return {
    state,
    consuming,
    total,
    sampled,
    // The loud one. A count from a sampled stream is an estimate, and a
    // dashboard that does not say so is a dashboard quietly lying.
    sampling: sampled ? `${sampled} sampled` : null,
    everything: consuming === total && sampled === 0,
  };
}

export default function useRunningStreams(dashboard, isLive) {
  const [streams, setStreams] = useState([]);
  const asking = !!(dashboard && dashboard.is_streaming && isLive);

  useEffect(() => {
    let live = true;
    if (!asking) {
      // Whatever was on screen describes a dashboard that has stopped.
      setStreams([]);
      return undefined;
    }
    const ask = () =>
      axios
        .get("api/streams/running")
        .then((data) => live && setStreams((data && data.streams) || []))
        .catch(() => {});
    ask();
    const timer = setInterval(ask, EVERY_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [asking]);

  const forQuery = useCallback((query) => streamsFor(query, streams)[0] || null, [streams]);

  // Only the topics this dashboard actually shows. A roll-up counting every
  // stream in the organisation would describe somebody else's board.
  const mine = useMemo(() => {
    const widgets = (dashboard && dashboard.widgets) || [];
    const found = [];
    widgets.forEach((widget) => {
      const query = widget.getQuery && widget.getQuery();
      streamsFor(query, streams).forEach((stream) => {
        if (!find(found, { id: stream.id })) {
          found.push(stream);
        }
      });
    });
    return found;
  }, [dashboard, streams]);

  return useMemo(() => ({ streams, forQuery, rollUp: rollUp(mine) }), [streams, forQuery, mine]);
}

/** What this widget's topic is doing, from the dashboard's one request. */
export function useStreamFor(query) {
  const context = useContext(StreamsContext);
  return context && query ? context.forQuery(query) : null;
}
