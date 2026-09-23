import React, { useMemo, useRef } from "react";
import cx from "classnames";
import { RendererPropTypes } from "@/visualizations/prop-types";
import { resolveColor, washColor } from "../shared/valueOptions";
import Problem from "../shared/components/Problem";
import buildTiles, { STATUS_SHAPES } from "./buildTiles";
import "./renderer.less";

export default function Renderer({ data, options }: any) {
  const { tiles, problem } = useMemo(() => buildTiles(data, options), [data, options]);

  // Colours from the previous refresh, so a tile whose state changed can say
  // so. Held in a ref: remembering it must not cause a render of its own.
  const previous = useRef<Record<string, string> | null>(null);
  const changed = useMemo(() => {
    const before = previous.current;
    const result = new Set<string>();
    if (before) {
      tiles.forEach((t) => {
        if (before[t.key] !== undefined && before[t.key] !== t.color) {
          result.add(t.key);
        }
      });
    }
    previous.current = Object.fromEntries(tiles.map((t) => [t.key, t.color]));
    return result;
  }, [tiles]);

  if (problem) {
    return <Problem>{problem}</Problem>;
  }

  return (
    <ul className={cx("status-grid", `status-grid-${options.tileSize}`)} aria-label="Status">
      {tiles.map((tile) => {
        const ink = resolveColor(tile.color);
        return (
          <li
            // Keyed by colour as well as name, so a tile that changes state is
            // a new element and its highlight animation plays again.
            key={`${tile.key}:${tile.color}`}
            className={cx("status-grid-tile", { "status-grid-tile-changed": changed.has(tile.key) })}
            style={{ background: washColor(tile.color), ["--tile-ink" as any]: ink }}
            data-test={`StatusGrid.Tile.${tile.key}`}
            data-status={tile.color}
          >
            <span className="status-grid-name" title={tile.name}>
              {tile.name}
            </span>
            {tile.value && <span className="status-grid-value">{tile.value}</span>}
            <span className="status-grid-status">
              <span aria-hidden="true">{STATUS_SHAPES[tile.color] || "●"}</span> {tile.status}
            </span>
            {tile.detail && (
              <span className="status-grid-detail" title={tile.detail}>
                {tile.detail}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

Renderer.propTypes = RendererPropTypes;
