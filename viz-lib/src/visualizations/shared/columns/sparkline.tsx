import React from "react";
import { toNumber, resolveColor, formatValue } from "../valueOptions";

/*
  A column of number series drawn as a small line in each cell: the last
  twenty readings of a metric beside its current value. The value can be a
  JSON array ("[1, 2, 3]"), an actual array (JSON columns), or a comma list
  ("1,2,3") -- whatever the query could produce with array_agg or string_agg.
*/

export function parseSeries(value: unknown): number[] {
  let items: unknown[] = [];
  if (Array.isArray(value)) {
    items = value;
  } else if (typeof value === "string") {
    const s = value.trim();
    if (s.startsWith("[")) {
      try {
        const parsed = JSON.parse(s);
        items = Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        items = [];
      }
    } else if (s.startsWith("{") && s.endsWith("}")) {
      // Postgres array literal: {1,2,3}
      items = s.slice(1, -1).split(",");
    } else if (s !== "") {
      items = s.split(",");
    }
  }
  return items.map((v) => toNumber(typeof v === "string" ? v.trim() : v)).filter((v): v is number => v !== null);
}

const WIDTH = 96;
const HEIGHT = 22;

/** Points scaled into a width x height box, oldest on the left. */
export function sparklineCoords(points: number[], width = WIDTH, height = HEIGHT): [number, number][] {
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  return points.map((v, i) => [
    (i / Math.max(1, points.length - 1)) * (width - 4) + 2,
    height - 3 - ((v - lo) / span) * (height - 6),
  ]);
}

export function sparklinePath(coords: [number, number][]): string {
  return coords.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
}

export default function initSparklineColumn(column: any) {
  function prepareData(row: any) {
    const points = parseSeries(row[column.name]);
    return { points, text: points.length ? formatValue(points[points.length - 1]) : "" };
  }

  function SparklineColumn({ row }: any) {
    // eslint-disable-line react/prop-types
    const { points, text } = prepareData(row);
    if (points.length < 2) {
      return <span className="table-cell-sparkline-empty">{text}</span>;
    }
    const color = resolveColor("accent");
    const coords = sparklineCoords(points);
    const last = coords[coords.length - 1];
    return (
      <svg
        className="table-cell-sparkline"
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Trend of ${points.length} values, latest ${text}`}
      >
        <title>{`Latest ${text}`}</title>
        <path d={sparklinePath(coords)} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
        <circle cx={last[0]} cy={last[1]} r={2.2} fill={color} />
      </svg>
    );
  }

  SparklineColumn.prepareData = prepareData;

  return SparklineColumn;
}

initSparklineColumn.friendlyName = "Sparkline";
