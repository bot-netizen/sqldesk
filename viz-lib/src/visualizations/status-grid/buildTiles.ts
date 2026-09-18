import { formatValue, thresholdColor, findMapping, SEMANTIC_COLORS, isSemanticColor } from "../shared/valueOptions";
import { hasColumn, ColumnLike } from "../shared/rows";
import { StatusGridOptions } from "./getOptions";

export interface Tile {
  /** Stable identity across refreshes: the name, de-duplicated. */
  key: string;
  name: string;
  /** What the tile shows in large type. */
  value: string;
  /** The status word under it. */
  status: string;
  detail: string;
  /** A colour name or CSS colour. */
  color: string;
}

/** Worst first. Custom colours sit between warning and good. */
const SEVERITY: Record<string, number> = { critical: 0, serious: 1, warning: 2, accent: 4, neutral: 5, good: 6 };

export function severityRank(color: string) {
  return color in SEVERITY ? SEVERITY[color] : 3;
}

// Shape as well as colour, so state reads for people who cannot tell the
// colours apart and in a greyscale screenshot.
export const STATUS_SHAPES: Record<string, string> = {
  good: "●",
  warning: "▲",
  serious: "◆",
  critical: "■",
  neutral: "○",
  accent: "●",
};

export function statusLabel(color: string): string {
  return isSemanticColor(color) ? SEMANTIC_COLORS[color].label : "";
}

export default function buildTiles(
  data: { columns: ColumnLike[]; rows: any[] },
  options: StatusGridOptions
): { tiles: Tile[]; problem: string | null } {
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { tiles: [], problem: "No rows to show." };
  }
  const columns = data.columns || [];
  const useName = hasColumn(columns, options.nameColumn);
  const useValue = hasColumn(columns, options.valueColumn);
  const useStatus = hasColumn(columns, options.statusColumn);
  const useDetail = hasColumn(columns, options.detailColumn);
  if (!useValue && !useStatus) {
    return { tiles: [], problem: "Choose a value column or a status column in the editor." };
  }

  const seen: Record<string, number> = {};
  const tiles = rows.map((row, i) => {
    const name = useName ? String(row[options.nameColumn] ?? "") : `Row ${i + 1}`;
    seen[name] = (seen[name] || 0) + 1;
    const key = seen[name] > 1 ? `${name}#${seen[name]}` : name;

    const raw = useValue ? row[options.valueColumn] : undefined;
    const statusRaw = useStatus ? row[options.statusColumn] : undefined;

    // A status column decides the colour when it maps to one; otherwise the
    // value's thresholds do. A mapping can also relabel the value itself.
    const statusMapping = useStatus ? findMapping(statusRaw, options.mappings) : null;
    const valueMapping = useValue ? findMapping(raw, options.mappings) : null;
    const color =
      (statusMapping && statusMapping.color) ||
      (valueMapping && valueMapping.color) ||
      (useValue ? thresholdColor(raw, options.thresholds) : null) ||
      "neutral";

    const value = useValue
      ? valueMapping && valueMapping.text
        ? valueMapping.text
        : formatValue(raw, options.valueFormat)
      : "";
    const status = useStatus ? (statusMapping && statusMapping.text) || String(statusRaw ?? "") : statusLabel(color);

    return {
      key,
      name,
      value,
      status,
      detail: useDetail ? String(row[options.detailColumn] ?? "") : "",
      color,
    };
  });

  if (options.sort === "severity") {
    // Stable: equal severities keep the query's order.
    tiles.sort((a, b) => severityRank(a.color) - severityRank(b.color));
  } else if (options.sort === "name") {
    tiles.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  }

  return { tiles, problem: null };
}
