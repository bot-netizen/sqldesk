import { isNil, extend, map, filter, groupBy, omit } from "lodash";

// d3 v3's `scale.category10`, which is all this file used d3 for. The ten
// colours are the same ones, kept so existing maps do not change colour.
const CATEGORY_10 = [
  "#1f77b4",
  "#ff7f0e",
  "#2ca02c",
  "#d62728",
  "#9467bd",
  "#8c564b",
  "#e377c2",
  "#7f7f7f",
  "#bcbd22",
  "#17becf",
];

/** Assigns a colour per distinct name, in the order names are first seen. */
function categoryColors() {
  const assigned = new Map<string, string>();
  return (name: string) => {
    if (!assigned.has(name)) {
      assigned.set(name, CATEGORY_10[assigned.size % CATEGORY_10.length]);
    }
    return assigned.get(name) as string;
  };
}

export default function prepareData(data: any, options: any) {
  const colorScale = categoryColors();

  const { classify, latColName, lonColName } = options;

  const pointGroups = classify ? groupBy(data.rows, classify) : { All: data.rows };

  return filter(
    map(pointGroups, (rows, name) => {
      const points = filter(
        map(rows, (row) => {
          const lat = row[latColName];
          const lon = row[lonColName];
          if (isNil(lat) || isNil(lon)) {
            return null;
          }
          return { lat, lon, row: omit(row, [latColName, lonColName]) };
        })
      );
      if (points.length === 0) {
        return null;
      }

      const result = extend({}, options.groups[name], { name, points });
      if (isNil(result.color)) {
        result.color = colorScale(name);
      }

      return result;
    })
  );
}
