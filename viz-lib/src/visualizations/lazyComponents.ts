import React from "react";
import { loadVisualization } from "./registeredVisualizations";

export type VisualizationPart = "Renderer" | "Editor";

const cache = new Map<string, React.ComponentType<any>>();

function nothing() {
  return null;
}

/**
 * A `React.lazy` wrapper around one part of one visualization, made once and
 * then kept.
 *
 * Kept, because React treats every lazy component as its own component type: a
 * fresh one on each render would unmount and remount whatever is underneath,
 * and a table would lose its page and a chart its zoom whenever the parent
 * re-rendered for an unrelated reason.
 *
 * Once the module has been fetched, `React.lazy` resolves without suspending,
 * so this costs a frame the first time a type is shown and nothing after.
 */
export default function lazyVisualizationComponent(type: string, part: VisualizationPart) {
  const key = `${type}:${part}`;
  const cached = cache.get(key);
  if (cached) {
    return cached;
  }
  const component = React.lazy(() =>
    // An Editor is optional: a visualization without one has nothing to show
    // in the settings pane, which is not an error.
    loadVisualization(type).then((components) => ({ default: components[part] || nothing }))
  );
  cache.set(key, component);
  return component;
}
