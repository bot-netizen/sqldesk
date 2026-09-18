import { useEffect, useState } from "react";
import resizeObserver from "@/services/resizeObserver";

export interface ElementSize {
  width: number;
  height: number;
}

/**
 * Track an element's size, for visualizations whose text should scale with
 * the widget rather than stay one size in a tile and a full-screen panel.
 * Pass the element from a ref callback held in state.
 */
export default function useElementSize(element: HTMLElement | null): ElementSize {
  const [size, setSize] = useState<ElementSize>({ width: 0, height: 0 });

  useEffect(() => {
    if (!element) {
      return;
    }
    const measure = () => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      setSize((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
    };
    measure();
    return resizeObserver(element, measure);
  }, [element]);

  return size;
}
