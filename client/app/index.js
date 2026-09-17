import React from "react";
import ReactDOM from "react-dom";

// Self-hosted via Fontsource rather than loaded from fonts.googleapis.com:
// SQLDesk is frequently deployed air-gapped, where a CDN dependency fails
// outright, and elsewhere it would leak viewer IPs to a third party.
// Variable fonts, so 400/500/600 all come from one file per subset, and
// Fontsource sets font-display: swap so text never blocks on them.
// The narrow entry points are deliberate: "standard"/"wght" carry the
// weight axis we use without the extra width and italic axes.
import "@fontsource-variable/instrument-sans/standard.css";
import "@fontsource-variable/jetbrains-mono/wght.css";

import "@/config";

import ApplicationArea from "@/components/ApplicationArea";
import offlineListener from "@/services/offline-listener";

ReactDOM.render(<ApplicationArea />, document.getElementById("application-root"), () => {
  offlineListener.init();
});
