/*
  One sanitizer, not two.

  This file used to be a byte-for-byte copy of viz-lib's. Both called
  `DOMPurify.addHook` at module scope, and both resolve to the same physical
  dompurify -- there is a single `dompurify@2.5.8` in the store -- so the hook
  was registered twice on one singleton and ran twice over every node. The
  hook happens to be idempotent, so nothing was wrong on screen; what was
  wrong is that two copies of a security-relevant rule could drift apart, and
  only one of them would be the one anybody edited.
*/
export { DOMPurify, default } from "@sqldesk/viz/lib/services/sanitize";
