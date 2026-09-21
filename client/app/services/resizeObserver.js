/*
  Watch elements for a change of size, by polling.

  One element can have several watchers, and that is not a rare case: an
  ECharts visualization registers twice for the same node -- once to resize the
  canvas, once to measure the box its option is built from. Keeping a single
  callback per node meant the second registration was dropped on the floor and
  its caller given a disposer that did nothing, with no error anywhere. The
  chart's canvas then kept whatever size it was created at: resize a widget and
  the tile changed while the chart inside it did not, and a chart created
  before its container had a width stayed 0x0 for good.
*/

// Each entry is { width, height, callbacks }; width and height are undefined
// until the first measurement, so the first pass always fires.
const items = new Map();

function checkItems() {
  if (items.size > 0) {
    items.forEach((item, node) => {
      const bounds = node.getBoundingClientRect();
      // convert to int (because these numbers needed for comparisons), but preserve 1 decimal point
      const width = Math.round(bounds.width * 10);
      const height = Math.round(bounds.height * 10);

      if (item.width !== width || item.height !== height) {
        item.width = width;
        item.height = height;
        // Copied before calling: a callback is allowed to stop watching, and
        // on a dashboard they do -- removing a widget disposes its watchers
        // from inside this loop.
        [...item.callbacks].forEach((callback) => callback(node));
      }
    });

    setTimeout(checkItems, 100);
  }
}

export default function observe(node, callback) {
  if (!node) {
    return () => {};
  }

  const shouldTrigger = items.size === 0;
  let item = items.get(node);
  if (!item) {
    item = { callbacks: new Set() };
    items.set(node, item);
  }
  item.callbacks.add(callback);

  if (shouldTrigger) {
    checkItems();
  }

  return () => {
    const watched = items.get(node);
    if (!watched) {
      return;
    }
    watched.callbacks.delete(callback);
    if (watched.callbacks.size === 0) {
      items.delete(node);
    }
  };
}
