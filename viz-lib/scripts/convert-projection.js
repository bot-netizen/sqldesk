// Converts the USA map from Mercator to Albers (USA).
//
// This is a one-off developer tool, not application code: it produced the
// committed `usa-albers.geo.json` and has no reason to run again unless the
// source map changes. It lived under src/ and was the last thing importing d3's
// geo projections, so it moved out here rather than keeping a whole mapping
// library installed for a script nobody runs.
//
// To run it, install the projections first -- they are deliberately not a
// dependency of this package:
//
//   npm install --no-save d3-geo
//   node scripts/convert-projection.js > src/visualizations/choropleth/maps/usa-albers.geo.json

const { each, map, filter } = require("lodash");
const { geoAlbersUsa, geoMercator } = require("d3-geo");

const albersUSA = geoAlbersUsa();
const mercator = geoMercator();

const geojson = require("../src/visualizations/choropleth/maps/usa.geo.json");

function convertPoint(coord: any) {
  const pt = albersUSA(coord);
  return pt ? mercator.invert(pt) : null;
}

function convertLineString(points: any) {
  return filter(map(points, convertPoint));
}

function convertPolygon(polygon: any) {
  return map(polygon, convertLineString);
}

function convertMultiPolygon(multiPolygon: any) {
  return map(multiPolygon, convertPolygon);
}

each(geojson.features, (feature: any) => {
  switch (feature.geometry.type) {
    case "Polygon":
      feature.geometry.coordinates = convertPolygon(feature.geometry.coordinates);
      break;
    case "MultiPolygon":
      feature.geometry.coordinates = convertMultiPolygon(feature.geometry.coordinates);
      break;
  }
});

console.log(JSON.stringify(geojson));
