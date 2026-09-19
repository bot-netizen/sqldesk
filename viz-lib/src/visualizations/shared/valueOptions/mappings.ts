/*
  Value mappings turn what a query returns into what a person should read:
  "0" into "Down", "degraded" into an amber tile. A status column rarely says
  "critical" -- it says whatever the system that wrote it says.

  Matching is on the text of the value, ignoring case and surrounding space,
  because the same status arrives as "OK", "ok" and "ok " from different
  sources.
*/

export interface ValueMapping {
  /** The value as the query returns it. */
  value: string;
  /** What to show instead. Empty keeps the original. */
  text: string;
  /** A colour name or CSS colour. Empty leaves colouring to thresholds. */
  color: string;
}

function key(value: unknown): string {
  return value === null || value === undefined ? "" : String(value).trim().toLowerCase();
}

export function normalizeMappings(mappings?: Partial<ValueMapping>[] | null): ValueMapping[] {
  return (Array.isArray(mappings) ? mappings : [])
    .filter((m) => m && typeof m.value === "string" && m.value.trim() !== "")
    .map((m) => ({
      value: String(m.value),
      text: m.text ? String(m.text) : "",
      color: m.color ? String(m.color) : "",
    }));
}

export function findMapping(value: unknown, mappings?: Partial<ValueMapping>[] | null): ValueMapping | null {
  const k = key(value);
  if (k === "") {
    return null;
  }
  return normalizeMappings(mappings).find((m) => key(m.value) === k) || null;
}
