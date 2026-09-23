import { useEffect, useRef, useState } from "react";
import resizeObserver from "@/services/resizeObserver";
import whenOnScreen from "@/services/offscreen";
import echarts from ".";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export interface UseEChartResult {
  /** Pass to a container's `ref`. */
  setContainer: (element: HTMLDivElement | null) => void;
  /** The live instance, or null before the container exists. */
  chart: any;
}

/**
 * Create a chart once, then push new options into it.
 *
 * Every ECharts visualization needs the same three things, and two of them are
 * easy to get wrong:
 *
 * - The instance must be **state, not a ref**. The container arrives through a
 *   ref callback, so creation happens on a later render than the first update
 *   attempt; held in a ref there is nothing to wake the update effect, and the
 *   chart is created but never given an option. That bug shipped once already.
 * - The chart is created once and kept. Rebuilding it on every data change is
 *   what stopped the old renderer animating: there was no previous state left
 *   to animate from.
 * - `signature` describes the shape of the data -- its series and categories.
 *   Unchanged means the points still mean the same thing, so values are merged
 *   and ECharts tweens between them. Changed means they do not, and animating
 *   between unrelated values would be a lie rather than a transition.
 *
 * Creation also waits for the container to come near the viewport, so a chart
 * scrolled past the bottom of a long dashboard costs nothing until it is
 * scrolled to. See `services/offscreen`. Once created it stays created.
 */
export default function useEChart(option: any, signature: string): UseEChartResult {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [chart, setChart] = useState<any>(null);
  // Latches: a chart that has been on screen once is never un-created.
  const [onScreen, setOnScreen] = useState(false);
  const signatureRef = useRef<string | null>(null);

  useEffect(() => {
    if (!container || onScreen) {
      return;
    }
    return whenOnScreen(container, () => setOnScreen(true));
  }, [container, onScreen]);

  useEffect(() => {
    if (!container || !onScreen) {
      return;
    }
    const instance = echarts.init(container, undefined, { renderer: "canvas" });
    // A fresh chart has no previous values, so the next update must replace
    // rather than try to tween from a state that does not exist.
    signatureRef.current = null;
    setChart(instance);

    const unwatch = resizeObserver(container, () => instance.resize());
    return () => {
      unwatch();
      instance.dispose();
    };
  }, [container, onScreen]);

  useEffect(() => {
    if (!chart) {
      return;
    }
    const sameShape = signatureRef.current === signature;
    // Every chart describes itself to screen readers unless it says otherwise:
    // without this a chart is an unlabelled canvas.
    const described = { aria: { enabled: true }, ...option };
    const next = prefersReducedMotion() ? { ...described, animation: false } : described;
    chart.setOption(next, { notMerge: !sameShape, lazyUpdate: true });
    signatureRef.current = signature;
  }, [chart, option, signature]);

  return { setContainer, chart };
}
