# @tealdash/viz

The visualizations used by [Tealdash](https://github.com/tdot-labs/tealdash): charts,
tables, cohorts, funnels, maps, pivot tables and the rest.

This is a workspace package of the Tealdash repository rather than something
published to npm. `client/` consumes it through pnpm's workspace protocol, and it
builds to two module formats — `lib/` (CommonJS, which jest can require) and
`esm/` (which webpack can tree-shake).

```bash
pnpm --filter @tealdash/viz test        # its own jest suite
pnpm run build:viz                      # build both outputs
```

Charts render with [Apache ECharts](https://echarts.apache.org/). A series type
has to be registered in `src/visualizations/echarts/index.ts` before it can be
drawn — the registration list is what keeps the bundle small, so adding one is a
deliberate act with a measurable cost.

## Usage

### Basic Usage

Rendering a visualization takes data, options and a type:

```jsx
import React, { useState } from "react";
import { Renderer, Editor } from "@tealdash/viz";

const exampleData = {
  columns: [
    { type: null, name: "Country" },
    { type: null, name: "Amount" },
  ],
  rows: [
    { Amount: 37.620000000000005, Country: "Argentina" },
    { Amount: 37.620000000000005, Country: "Australia" },
    { Amount: 42.62, Country: "Austria" },
    { Amount: 37.62, Country: "Belgium" },
    { Amount: 190.09999999999997, Country: "Brazil" },
    { Amount: 303.9599999999999, Country: "Canada" },
    { Amount: 46.62, Country: "Chile" },
    { Amount: 90.24000000000001, Country: "Czech Republic" },
    { Amount: 37.620000000000005, Country: "Denmark" },
    { Amount: 41.620000000000005, Country: "Finland" },
    { Amount: 195.09999999999994, Country: "France" },
  ],
};

function Example() {
  const [options, setOptions] = useState({ countRows: true });

  return (
    <div>
      <Editor
        type="COUNTER"
        visualizationName="Example Visualization"
        options={options}
        data={exampleData}
        onChange={setOptions}
      />
      <Renderer type="COUNTER" visualizationName="Example Visualization" options={options} data={exampleData} />
    </div>
  );
}
```

### Available Types

- Chart: `CHART`
- Cohort: `COHORT`
- Counter: `COUNTER`
- Details View: `DETAILS`
- Funnel: `FUNNEL`
- Map (Choropleth): `CHOROPLETH`
- Map (Markers): `MAP`
- Pivot Table: `PIVOT`
- Sankey: `SANKEY`
- Sunburst Sequence: `SUNBURST_SEQUENCE`
- Table: `TABLE`
- Word Cloud: `WORD_CLOUD`

### Column Types

Types used for the `columns` property in the `data` object. Currently used to determine the default column view for the Table Visualization. This field is not mandatory and can receive a `null` value.

Example:

```js
const data = {
  columns: [
    { type: "string", name: "Country" },
    { type: "float", name: "Amount" },
  ],
  rows: [],
};
```

Available types:

- `integer`
- `float`
- `boolean`
- `string`
- `datetime`
- `date`

### Customizable Settings

| Option                     | Description                                                                                     | Type                                                           | Default                                                                                                                                                                        |
| -------------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| dateFormat                 | Date Format                                                                                     | `string`                                                       | `"DD/MM/YYYY"`                                                                                                                                                                 |
| dateTimeFormat             | DateTime Format                                                                                 | `string`                                                       | `"DD/MM/YYYY HH:mm"`                                                                                                                                                           |
| integerFormat              | Integer Format                                                                                  | `string`                                                       | `"0,0"`                                                                                                                                                                        |
| floatFormat                | Float Format                                                                                    | `string`                                                       | `"0,0.00"`                                                                                                                                                                     |
| booleanValues              | Boolean names                                                                                   | `Array [string, string]` (correspond to false and true values) | `["false", "true"]`                                                                                                                                                            |
| tableCellMaxJSONSize       | Max json size that will be parsed and rendered in a Table Cell                                  | `integer`                                                      | `50000`                                                                                                                                                                        |
| allowCustomJSVisualization | Whether to allow the `Custom` chart type                                                        | `boolean`                                                      | `false`                                                                                                                                                                        |
| hidePlotlyModeBar          | Whether to hide the Plotly Mode Bar on charts                                                   | `boolean`                                                      | `false`                                                                                                                                                                        |
| choroplethAvailableMaps    | Configure the JSONs used for Choropleth maps (Note: Choropleth won't work without this setting) | `Object` (see example below)                                   | `{}`                                                                                                                                                                           |
| HelpTriggerComponent       | Component used to render helper links on the Editor                                             | React component with `title` and `href` props                  | Renders a [tooltip with a link](https://github.com/tdot-labs/tealdash/blob/fc246aafc445bdfc3ad2b82560141ef51f8753a9/viz-lib/src/visualizations/visualizationsSettings.js#L6-L33) |

Example:

```jsx
import React from "react";
import { Renderer, Editor, updateVisualizationsSettings } from "@tealdash/viz";

import countriesDataUrl from "@tealdash/viz/lib/visualizations/choropleth/maps/countries.geo.json";
import subdivJapanDataUrl from "@tealdash/viz/lib/visualizations/choropleth/maps/japan.prefectures.geo.json";

function wrapComponentWithSettings(WrappedComponent) {
  return function VisualizationComponent(props) {
    updateVisualizationsSettings({
      choroplethAvailableMaps: {
        countries: {
          name: "Countries",
          url: countriesDataUrl,
        },
        subdiv_japan: {
          name: "Japan/Prefectures",
          url: subdivJapanDataUrl,
        },
      },
      dateFormat: "YYYY/MM/DD",
      booleanValues: ["False", "True"],
      hidePlotlyModeBar: true,
    });

    return <WrappedComponent {...props} />;
  };
}

export const ConfiguredRenderer = wrapComponentWithSettings(Renderer);
export const ConfiguredEditor = wrapComponentWithSettings(Editor);
```

### Specific File Imports

There is a transpiled only build aimed for specific file imports.

**Note:** Currently requires Less.

Usage:

```jsx
import React from "react";
import JsonViewInteractive from "@tealdash/viz/lib/components/json-view-interactive/JsonViewInteractive";

const example = { list: ["value1", "value2", "value3"], obj: { prop: "value" } };

export default function App() {
  return <JsonViewInteractive value={example} />;
}
```

## License

BSD-2-Clause.
