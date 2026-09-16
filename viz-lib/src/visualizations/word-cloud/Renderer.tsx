import cloud from "d3-cloud";
import { each, filter, map, min, max, sortBy, toString } from "lodash";
import React, { useMemo, useState, useEffect } from "react";
import resizeObserver from "@/services/resizeObserver";
import { RendererPropTypes } from "@/visualizations/prop-types";

import "./renderer.less";

const MIN_WORD_SIZE = 10;
const MAX_WORD_SIZE = 100;

// d3 v3's `scale.category20`, the only palette this file took from d3. Kept
// verbatim so existing word clouds keep their colours.
const CATEGORY_20 = [
  "#1f77b4",
  "#aec7e8",
  "#ff7f0e",
  "#ffbb78",
  "#2ca02c",
  "#98df8a",
  "#d62728",
  "#ff9896",
  "#9467bd",
  "#c5b0d5",
  "#8c564b",
  "#c49c94",
  "#e377c2",
  "#f7b6d2",
  "#7f7f7f",
  "#c7c7c7",
  "#bcbd22",
  "#dbdb8d",
  "#17becf",
  "#9edae5",
];

/** d3 v3's `scale.linear`, for the one mapping this file needs. */
function linearScale([fromMin, fromMax]: any[], [toMin, toMax]: number[]) {
  const span = (fromMax as number) - (fromMin as number);
  return (value: number) => {
    // A single distinct count has no range to scale across; d3 returned the
    // midpoint of the output range, and so does this.
    if (!span) {
      return (toMin + toMax) / 2;
    }
    return toMin + ((value - (fromMin as number)) / span) * (toMax - toMin);
  };
}

function computeWordFrequencies(rows: any, column: any) {
  const result = {};

  each(rows, (row) => {
    const wordsList = toString(row[column]).split(/\s/g);
    each(wordsList, (d) => {
      // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
      result[d] = (result[d] || 0) + 1;
    });
  });

  return result;
}

function getWordsWithFrequencies(rows: any, wordColumn: any, frequencyColumn: any) {
  const result = {};

  each(rows, (row) => {
    const count = parseFloat(row[frequencyColumn]);
    if (Number.isFinite(count) && count > 0) {
      const word = toString(row[wordColumn]);
      // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
      result[word] = count;
    }
  });

  return result;
}

function applyLimitsToWords(words: any, { wordLength, wordCount }: any) {
  wordLength.min = Number.isFinite(wordLength.min) ? wordLength.min : null;
  wordLength.max = Number.isFinite(wordLength.max) ? wordLength.max : null;

  wordCount.min = Number.isFinite(wordCount.min) ? wordCount.min : null;
  wordCount.max = Number.isFinite(wordCount.max) ? wordCount.max : null;

  return filter(words, ({ text, count }) => {
    const wordLengthFits =
      (!wordLength.min || text.length >= wordLength.min) && (!wordLength.max || text.length <= wordLength.max);
    const wordCountFits = (!wordCount.min || count >= wordCount.min) && (!wordCount.max || count <= wordCount.max);
    return wordLengthFits && wordCountFits;
  });
}

function prepareWords(rows: any, options: any) {
  let result: any = [];

  if (options.column) {
    if (options.frequenciesColumn) {
      result = getWordsWithFrequencies(rows, options.column, options.frequenciesColumn);
    } else {
      result = computeWordFrequencies(rows, options.column);
    }
    result = sortBy(
      map(result, (count, text) => ({ text, count })),
      [({ count }: any) => -count, ({ text }: any) => -text.length] // "count" desc, length("text") desc
    );
  }

  // Add additional attributes
  const counts = map(result, (item) => item.count);
  const wordSize = linearScale([min(counts), max(counts)], [MIN_WORD_SIZE, MAX_WORD_SIZE]);

  each(result, (item, key) => {
    // `result` is an array by this point, but lodash types the key as
    // string|number because it also accepts objects.
    const index = Number(key);
    item.size = wordSize(item.count);
    item.color = CATEGORY_20[index % CATEGORY_20.length];
    item.angle = (index % 2) * 90; // make it stable between renderings
  });

  return applyLimitsToWords(result, {
    wordLength: options.wordLengthLimit,
    wordCount: options.wordCountLimit,
  });
}

function scaleElement(node: any, container: any) {
  node.style.transform = null;
  const { width: nodeWidth, height: nodeHeight } = node.getBoundingClientRect();
  const { width: containerWidth, height: containerHeight } = container.getBoundingClientRect();

  const scaleX = containerWidth / nodeWidth;
  const scaleY = containerHeight / nodeHeight;

  node.style.transform = `scale(${Math.min(scaleX, scaleY)})`;
}

function createLayout() {
  const fontFamily = window.getComputedStyle(document.body).fontFamily;

  return (
    cloud()
      // make the area large enough to contain even very long words; word cloud will be placed in the center of the area
      // TODO: dimensions probably should be larger, but `d3-cloud` has some performance issues related to these values
      .size([5000, 5000])
      .padding(3)
      .font(fontFamily)
      .rotate((d: any) => d.angle)
      .fontSize((d: any) => d.size)
      .random(() => 0.5)
  ); // do not place words randomly - use compact layout
}

const SVG_NS = "http://www.w3.org/2000/svg";

function render(container: any, words: any) {
  container.innerHTML = "";

  const svg = document.createElementNS(SVG_NS, "svg");
  const g = document.createElementNS(SVG_NS, "g");
  svg.appendChild(g);
  container.appendChild(svg);

  each(words, (word: any) => {
    const text = document.createElementNS(SVG_NS, "text");
    text.style.fontSize = `${word.size}px`;
    text.style.fontFamily = word.font;
    text.style.fill = word.color;
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("transform", `translate(${[word.x, word.y]}) rotate(${word.rotate})`);
    text.textContent = word.text;
    g.appendChild(text);
  });

  const svgBounds = svg.getBoundingClientRect();
  const gBounds = g.getBoundingClientRect();

  svg.setAttribute("width", String(Math.ceil(gBounds.width)));
  svg.setAttribute("height", String(Math.ceil(gBounds.height)));
  g.setAttribute("transform", `translate(${svgBounds.left - gBounds.left},${svgBounds.top - gBounds.top})`);

  scaleElement(svg, container);
}

export default function Renderer({ data, options }: any) {
  const [container, setContainer] = useState(null);
  const [words, setWords] = useState([]);
  const layout = useMemo(createLayout, []);

  // @ts-expect-error ts-migrate(2345) FIXME: Argument of type '() => () => layout.Cloud<cloud.W... Remove this comment to see the full error message
  useEffect(() => {
    layout
      .words(prepareWords(data.rows, options))
      // @ts-expect-error ts-migrate(2345) FIXME: Argument of type 'Word[]' is not assignable to par... Remove this comment to see the full error message
      .on("end", (w) => setWords(w))
      .start();
    // @ts-expect-error ts-migrate(2769) FIXME: No overload matches this call.
    return () => layout.on("end", null).stop();
  }, [layout, data, options, setWords]);

  useEffect(() => {
    if (container) {
      render(container, words);
    }
  }, [container, words]);

  useEffect(() => {
    if (container) {
      const unwatch = resizeObserver(container, () => {
        // @ts-expect-error ts-migrate(2531) FIXME: Object is possibly 'null'.
        const svg = container.querySelector("svg");
        if (svg) {
          scaleElement(svg, container);
        }
      });
      return unwatch;
    }
  }, [container]);

  // @ts-expect-error ts-migrate(2322) FIXME: Type 'Dispatch<SetStateAction<null>>' is not assig... Remove this comment to see the full error message
  return <div className="word-cloud-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
