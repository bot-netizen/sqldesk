import React from "react";
import { pick } from "lodash";
import HelpTrigger from "@/components/HelpTrigger";
import Link from "@/components/Link";
import { Renderer as VisRenderer, Editor as VisEditor, updateVisualizationsSettings } from "@sqldesk/viz/lib";
import { revealAllCharts } from "@sqldesk/viz/lib/services/offscreen";
import { inScreenshotMode } from "@/lib/hooks/useScreenshotMode";
import { clientConfig } from "@/services/auth";

import countriesDataUrl from "@sqldesk/viz/lib/visualizations/choropleth/maps/countries.geo.json";
import usaDataUrl from "@sqldesk/viz/lib/visualizations/choropleth/maps/usa-albers.geo.json";
import subdivJapanDataUrl from "@sqldesk/viz/lib/visualizations/choropleth/maps/japan.prefectures.geo.json";

// Charts are normally built only once they come near the viewport. A page
// being photographed is captured whole, including the part below the window,
// so a deferred chart would be a blank rectangle in the image. Once, on the
// first visualization to render: the flag never goes back.
let revealed = false;
function revealForScreenshotOnce() {
  if (!revealed && inScreenshotMode()) {
    revealed = true;
    revealAllCharts();
  }
}

function wrapComponentWithSettings(WrappedComponent) {
  return function VisualizationComponent(props) {
    revealForScreenshotOnce();
    updateVisualizationsSettings({
      HelpTriggerComponent: HelpTrigger,
      LinkComponent: Link,
      choroplethAvailableMaps: {
        countries: {
          name: "Countries",
          url: countriesDataUrl,
          fieldNames: {
            name: "Short name",
            name_long: "Full name",
            abbrev: "Abbreviated name",
            iso_a2: "ISO code (2 letters)",
            iso_a3: "ISO code (3 letters)",
            iso_n3: "ISO code (3 digits)",
          },
        },
        usa: {
          name: "USA",
          url: usaDataUrl,
          fieldNames: {
            name: "Name",
            ns_code: "National Standard ANSI Code (8-character)",
            geoid: "Geographic ID",
            usps_abbrev: "USPS Abbreviation",
            fips_code: "FIPS Code (2-character)",
          },
        },
        subdiv_japan: {
          name: "Japan/Prefectures",
          url: subdivJapanDataUrl,
          fieldNames: {
            name: "Name",
            name_alt: "Name (alternative)",
            name_local: "Name (local)",
            iso_3166_2: "ISO-3166-2",
            postal: "Postal Code",
            type: "Type",
            type_en: "Type (EN)",
            region: "Region",
            region_code: "Region Code",
          },
        },
      },
      ...pick(clientConfig, [
        "dateFormat",
        "dateTimeFormat",
        "integerFormat",
        "floatFormat",
        "thousandsSeparator",
        "decimalSeparator",
        "nullValue",
        "booleanValues",
        "tableCellMaxJSONSize",
      ]),
    });

    return <WrappedComponent {...props} />;
  };
}

export const Renderer = wrapComponentWithSettings(VisRenderer);
export const Editor = wrapComponentWithSettings(VisEditor);
