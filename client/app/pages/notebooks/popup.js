/*
  Where a dropdown's overlay lives.

  antd puts an overlay in a portal on `document.body` and positions it when it
  opens. The window is not this app's scroller -- `.application-layout-content`
  is, with `overflow-y: auto` -- so an overlay anchored to the body does not
  travel with the thing that opened it, and on a long notebook it ends up
  somewhere down the page away from its own control.

  `.notebook-page` is the container to hang them on. It wraps everything on the
  page, it scrolls with the cells because it is inside the scroller rather than
  being one, and nothing on it clips: `.notebook-cell` sets `overflow: hidden`
  for its rounded corners, so an overlay hung inside a cell would be cut off at
  the cell's edge instead.

  Falls back to the body, which is antd's own default, so a cell rendered
  outside a notebook page (a test, a dialog) still opens its menus.
*/
export default function popupInPage(trigger) {
  return (trigger && trigger.closest && trigger.closest(".notebook-page")) || document.body;
}
