/*
  One watcher, not two.

  This file used to be a byte-for-byte copy of viz-lib's, which meant two
  independent polling loops and two separate registries -- an element watched
  through one was invisible to the other. Re-exported so the whole application
  shares a single loop.
*/
export { default } from "@sqldesk/viz/lib/services/resizeObserver";
