import { values } from "lodash";

// Define color palettes
export const BaseColors = {
  Blue: "#356AFF",
  Red: "#E92828",
  Green: "#3BD973",
  Purple: "#604FE9",
  Cyan: "#50F5ED",
  Orange: "#FB8D3D",
  "Light Blue": "#799CFF",
  Lilac: "#B554FF",
  "Light Green": "#8CFFB4",
  Brown: "#A55F2A",
  Black: "#000000",
  Gray: "#494949",
  Pink: "#FF7DE3",
  "Dark Blue": "#002FB4",
};

// Additional colors for the user to choose from
export const AdditionalColors = {
  "Indian Red": "#981717",
  "Green 2": "#17BF51",
  "Green 3": "#049235",
  "Dark Turquoise": "#00B6EB",
  "Dark Violet": "#A58AFF",
  "Pink 2": "#C63FA9",
};

const Viridis = {
  1: "#440154",
  2: "#48186a",
  3: "#472d7b",
  4: "#424086",
  5: "#3b528b",
  6: "#33638d",
  7: "#2c728e",
  8: "#26828e",
  9: "#21918c",
  10: "#1fa088",
  11: "#28ae80",
  12: "#3fbc73",
  13: "#5ec962",
  14: "#84d44b",
  15: "#addc30",
  16: "#d8e219",
  17: "#fde725",
};

const Tableau = {
  1: "#4e79a7",
  2: "#f28e2c",
  3: "#e15759",
  4: "#76b7b2",
  5: "#59a14f",
  6: "#edc949",
  7: "#af7aa1",
  8: "#ff9da7",
  9: "#9c755f",
  10: "#bab0ab",
};

const D3Category10 = {
  1: "#1f77b4",
  2: "#ff7f0e",
  3: "#2ca02c",
  4: "#d62728",
  5: "#9467bd",
  6: "#8c564b",
  7: "#e377c2",
  8: "#7f7f7f",
  9: "#bcbd22",
  10: "#17becf",
};

let ColorPalette = {
  ...BaseColors,
  ...AdditionalColors,
};

export const ColorPaletteArray = values(ColorPalette);

export default ColorPalette;

export const AllColorPalettes = {
  SQLDesk: ColorPalette,
  Viridis: Viridis,
  "Tableau 10": Tableau,
  "D3 Category 10": D3Category10,
};

export const AllColorPaletteArrays = {
  SQLDesk: ColorPaletteArray,
  Viridis: values(Viridis),
  "Tableau 10": values(Tableau),
  "D3 Category 10": values(D3Category10),
};

export const ColorPaletteTypes = {
  SQLDesk: "discrete",
  Viridis: "continuous",
  "Tableau 10": "discrete",
  "D3 Category 10": "discrete",
};

export const DEFAULT_COLOR_SCHEME = "SQLDesk";

// Chart options persist the scheme by name. Charts saved before the rename carry
// "Redash", and anything imported or created through the API can name a palette
// that does not exist. A lookup on either returned undefined and the next
// `palette.length` took down the whole dashboard the chart sat on -- so every
// name is resolved to a real palette first.
//
// Aliases live here rather than as extra keys on AllColorPalettes because the
// editor lists that object's keys; a key would put "Redash" back in the dropdown.
const LEGACY_COLOR_SCHEMES: { [name: string]: string } = {
  Tealdash: DEFAULT_COLOR_SCHEME,
  Redash: DEFAULT_COLOR_SCHEME,
};

export function resolveColorScheme(name: any): string {
  if (typeof name === "string") {
    if (Object.prototype.hasOwnProperty.call(AllColorPaletteArrays, name)) {
      return name;
    }
    if (Object.prototype.hasOwnProperty.call(LEGACY_COLOR_SCHEMES, name)) {
      return LEGACY_COLOR_SCHEMES[name];
    }
  }
  return DEFAULT_COLOR_SCHEME;
}
