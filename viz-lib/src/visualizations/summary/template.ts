import { find, isFinite, isNil, isString, minBy, toString } from "lodash";
import moment from "moment/moment";
import { createNumberFormatter } from "@/lib/value-format";
import { visualizationsSettings } from "@/visualizations/visualizationsSettings";

/*
  A sentence with the query's numbers in it.

  "Revenue this week is {{ sum(revenue) | currency }}, {{ change | percent | arrow }}
  on last week." -- written once, true every time the query refreshes.

  The grammar is small on purpose, because the person writing it is writing a
  sentence, not a program:

    {{ column }}                       the first row's value
    {{ sum(column) }}                  sum, avg, min, max, count over every row
    {{ count() }}                      how many rows
    {{ column where region = "West" }} the first row where region is West
    {{ ... | currency | arrow }}       formatted, left to right
    {{ ... | number | suffix(%) }}     with a unit inside its colour

  Every value is text by the time it reaches the page -- never markup -- so a
  query result cannot put anything on a dashboard but words.

  Anything that cannot be worked out becomes a *problem* in the sentence, in
  place, saying what is wrong: "revnue isn't in this result -- did you mean
  revenue?". A blank where a number should be is how a broken summary goes
  unnoticed for a month.
*/

export type Tone = "good" | "bad" | "watch" | "neutral";
export type Icon = "none" | "up" | "down" | "check" | "alert";
export type Operator = ">" | ">=" | "<" | "<=" | "=" | "!=" | "between";

export interface Rule {
  column: string;
  op: Operator;
  value?: any;
  value2?: any;
  tone: Tone;
  icon?: Icon;
}

export type Piece =
  | { kind: "text"; text: string }
  | { kind: "value"; text: string; tone: Tone | null; icon: Icon | null; expression: string }
  | { kind: "problem"; text: string; expression: string };

export const AGGREGATES = ["sum", "avg", "min", "max", "count"] as const;
export const FILTERS = [
  "number",
  "integer",
  "currency",
  "percent",
  "round",
  "date",
  "datetime",
  "upper",
  "lower",
  "prefix",
  "suffix",
  "arrow",
] as const;

/** Up and down, as glyphs: they survive a picture in Slack, an email and a PDF. */
export const GLYPHS: Record<string, string> = { up: "▲", down: "▼", check: "✓", alert: "⚠" };

const EXPRESSION = /\{\{\s*([\s\S]*?)\s*\}\}/g;
const HEAD = /^(?:(sum|avg|min|max|count)\s*\(\s*([^()]*?)\s*\)|([^\s|()]+))\s*/i;
const WHERE = /^where\s+([^\s=!]+)\s*(=|!=)\s*("([^"]*)"|'([^']*)'|([^\s|]+))\s*/i;
const FILTER = /^\|\s*([a-z_]+)\s*(?:\(\s*([^)]*?)\s*\))?\s*/i;

interface Column {
  name: string;
  type?: string;
}

interface Data {
  columns?: Column[];
  rows?: any[];
}

interface Parsed {
  aggregate: string | null;
  column: string | null;
  where: { column: string; op: "=" | "!="; value: string } | null;
  filters: { name: string; arg: string | null }[];
}

/** The template, split into words and `{{ ... }}`s, in order. */
export function split(template: string): { kind: "text" | "expression"; text: string }[] {
  const parts: { kind: "text" | "expression"; text: string }[] = [];
  let last = 0;
  (template || "").replace(EXPRESSION, (match: string, inner: string, offset: number) => {
    if (offset > last) {
      parts.push({ kind: "text", text: template.slice(last, offset) });
    }
    parts.push({ kind: "expression", text: inner });
    last = offset + match.length;
    return match;
  });
  if (last < (template || "").length) {
    parts.push({ kind: "text", text: template.slice(last) });
  }
  return parts;
}

export function parseExpression(source: string): Parsed | string {
  let rest = source.trim();
  const head = HEAD.exec(rest);
  if (!head) {
    return "Nothing to show: put a column's name between {{ and }}.";
  }
  rest = rest.slice(head[0].length);
  const parsed: Parsed = {
    aggregate: head[1] ? head[1].toLowerCase() : null,
    column: head[1] ? head[2] || null : head[3],
    where: null,
    filters: [],
  };
  if (parsed.aggregate && parsed.aggregate !== "count" && !parsed.column) {
    return `${parsed.aggregate}() needs a column: ${parsed.aggregate}(revenue).`;
  }

  const where = WHERE.exec(rest);
  if (where) {
    const value = where[4] !== undefined ? where[4] : where[5] !== undefined ? where[5] : where[6];
    parsed.where = { column: where[1], op: where[2] as "=" | "!=", value };
    rest = rest.slice(where[0].length);
  }

  while (rest.length) {
    const filter = FILTER.exec(rest);
    if (!filter) {
      return `"${rest}" isn't something a value can be followed by. Use | and a format, like | currency.`;
    }
    const name = filter[1].toLowerCase();
    if (!(FILTERS as readonly string[]).includes(name)) {
      return `"${filter[1]}" isn't a format. Try one of: ${FILTERS.join(", ")}.`;
    }
    parsed.filters.push({ name, arg: filter[2] || null });
    rest = rest.slice(filter[0].length);
  }
  return parsed;
}

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_unused, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    let previous = i - 1;
    row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const kept = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1));
      previous = kept;
    }
  }
  return row[b.length];
}

/** The column this name means: exactly, else ignoring case, else a suggestion. */
export function resolveColumn(name: string, columns: Column[]): { column: Column | null; problem: string | null } {
  const exact = find(columns, { name });
  if (exact) {
    return { column: exact, problem: null };
  }
  const loose = find(columns, (column) => column.name.toLowerCase() === name.toLowerCase());
  if (loose) {
    return { column: loose, problem: null };
  }
  const nearest = minBy(columns, (column) => distance(column.name.toLowerCase(), name.toLowerCase()));
  const close = nearest && distance(nearest.name.toLowerCase(), name.toLowerCase()) <= 3;
  return {
    column: null,
    problem: close ? `${name} isn't in this result — did you mean ${nearest!.name}?` : `${name} isn't in this result.`,
  };
}

function asNumber(value: any): number | null {
  if (isFinite(value)) {
    return value;
  }
  if (isString(value) && value.trim() !== "" && isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

function same(a: any, b: any): boolean {
  const left = asNumber(a);
  const right = asNumber(b);
  if (left !== null && right !== null) {
    return left === right;
  }
  return toString(a).trim().toLowerCase() === toString(b).trim().toLowerCase();
}

/** Whether a rule holds for this value. */
export function matches(rule: Rule, value: any): boolean {
  if (isNil(value)) {
    return false;
  }
  if (rule.op === "=") {
    return same(value, rule.value);
  }
  if (rule.op === "!=") {
    return !same(value, rule.value);
  }
  const number = asNumber(value);
  const bound = asNumber(rule.value);
  if (number === null || bound === null) {
    return false;
  }
  switch (rule.op) {
    case ">":
      return number > bound;
    case ">=":
      return number >= bound;
    case "<":
      return number < bound;
    case "<=":
      return number <= bound;
    case "between": {
      const upper = asNumber(rule.value2);
      if (upper === null) {
        return false;
      }
      return number >= Math.min(bound, upper) && number <= Math.max(bound, upper);
    }
    default:
      return false;
  }
}

function aggregate(name: string, values: any[], rowCount: number): any {
  if (name === "count") {
    return rowCount;
  }
  const numbers = values.map(asNumber).filter((n): n is number => n !== null);
  if (!numbers.length) {
    return null;
  }
  switch (name) {
    case "sum":
      return numbers.reduce((a, b) => a + b, 0);
    case "avg":
      return numbers.reduce((a, b) => a + b, 0) / numbers.length;
    case "min":
      return Math.min(...numbers);
    case "max":
      return Math.max(...numbers);
    default:
      return null;
  }
}

function formatByType(value: any, type: string | undefined): string {
  if (isNil(value)) {
    return "—";
  }
  const number = asNumber(value);
  if ((type === "integer" || type === "float" || (type === undefined && number !== null)) && number !== null) {
    const format =
      type === "integer" || Number.isInteger(number)
        ? visualizationsSettings.integerFormat
        : visualizationsSettings.floatFormat;
    return toString(createNumberFormatter(format)(number));
  }
  if (type === "datetime" || type === "date") {
    const when = moment(value);
    if (when.isValid()) {
      return when.format(type === "date" ? visualizationsSettings.dateFormat : visualizationsSettings.dateTimeFormat);
    }
  }
  return toString(value);
}

function applyFilters(value: any, type: string | undefined, filters: Parsed["filters"]) {
  let text: string | null = null;
  let icon: Icon | null = null;
  const number = asNumber(value);
  for (const filter of filters) {
    if (isNil(value)) {
      break;
    }
    switch (filter.name) {
      case "number":
        text = number === null ? toString(value) : toString(createNumberFormatter("0,0.[00]")(number));
        break;
      case "integer":
        text = number === null ? toString(value) : toString(createNumberFormatter("0,0")(Math.round(number)));
        break;
      case "round": {
        const places = Math.max(0, Math.min(10, parseInt(filter.arg || "0", 10) || 0));
        const format = places ? `0,0.${"0".repeat(places)}` : "0,0";
        text = number === null ? toString(value) : toString(createNumberFormatter(format)(number));
        break;
      }
      case "currency": {
        const symbol = filter.arg || "$";
        if (number !== null) {
          const amount = toString(createNumberFormatter("0,0.[00]")(Math.abs(number)));
          text = `${number < 0 ? "-" : ""}${symbol}${amount}`;
        }
        break;
      }
      case "percent":
        // A fraction, as the app's own percent format reads one: 0.124 is
        // 12.4%. A column already in percent is `{{ change | number }}%`.
        // Multiplied here: the app's own number format appends a % sign and
        // does not scale, so "0.[0]%" would print 0.124 as "0.1%".
        text = number === null ? toString(value) : `${toString(createNumberFormatter("0,0.[0]")(number * 100))}%`;
        break;
      case "date":
      case "datetime": {
        const when = moment(value);
        if (when.isValid()) {
          text = when.format(
            filter.name === "date" ? visualizationsSettings.dateFormat : visualizationsSettings.dateTimeFormat
          );
        }
        break;
      }
      case "upper":
        text = (text === null ? formatByType(value, type) : text).toUpperCase();
        break;
      case "lower":
        text = (text === null ? formatByType(value, type) : text).toLowerCase();
        break;
      case "prefix":
      case "suffix": {
        // A unit that belongs with the number -- "100%", "3 days", "x2" --
        // inside its colour rather than outside it.
        const word = (filter.arg || "").replace(/^["']|["']$/g, "");
        const shown: string = text === null ? formatByType(value, type) : text;
        text = filter.name === "prefix" ? `${word}${shown}` : `${shown}${word}`;
        break;
      }
      case "arrow":
        if (number !== null && number !== 0) {
          icon = number > 0 ? "up" : "down";
        }
        break;
      default:
        break;
    }
  }
  return { text: text === null ? formatByType(value, type) : text, icon };
}

/**
 * One `{{ ... }}`, worked out against the result: its words, and the tone and
 * icon the first matching rule gives it.
 */
export function evaluate(source: string, data: Data, rules: Rule[] = []): Piece {
  const expression = `{{ ${source.trim()} }}`;
  const parsed = parseExpression(source);
  if (isString(parsed)) {
    return { kind: "problem", text: parsed, expression };
  }
  const columns = data.columns || [];
  let rows = data.rows || [];

  if (parsed.where) {
    const { column, problem } = resolveColumn(parsed.where.column, columns);
    if (!column) {
      return { kind: "problem", text: problem!, expression };
    }
    const wanted = parsed.where;
    rows = rows.filter((row) =>
      wanted.op === "=" ? same(row[column.name], wanted.value) : !same(row[column.name], wanted.value)
    );
  }

  let column: Column | null = null;
  if (parsed.column) {
    const resolved = resolveColumn(parsed.column, columns);
    if (!resolved.column) {
      return { kind: "problem", text: resolved.problem!, expression };
    }
    column = resolved.column;
  }

  let value: any;
  let type = column ? column.type : undefined;
  if (parsed.aggregate) {
    value = aggregate(
      parsed.aggregate,
      column ? rows.map((row) => row[column!.name]) : [],
      parsed.column ? rows.filter((row) => !isNil(row[column!.name])).length : rows.length
    );
    type =
      parsed.aggregate === "count" ? "integer" : type === "integer" && parsed.aggregate !== "avg" ? "integer" : "float";
  } else {
    value = rows.length ? rows[0][column!.name] : null;
  }

  const { text, icon: arrow } = applyFilters(value, type, parsed.filters);
  // A rule is about a column; an aggregate is about the column inside it, and
  // count() about "count".
  const ruleColumn = column ? column.name : parsed.aggregate || "";
  const rule = find(rules || [], (one) => one && one.column === ruleColumn && matches(one, value));
  const icon = rule && rule.icon && rule.icon !== "none" ? rule.icon : arrow;
  return { kind: "value", text, tone: rule ? rule.tone : null, icon, expression };
}

/** The whole template, worked out: words and values in order. */
export function render(template: string, data: Data, rules: Rule[] = []): Piece[] {
  return split(template).map((part) =>
    part.kind === "text" ? { kind: "text", text: part.text } : evaluate(part.text, data, rules)
  );
}

/**
 * A first template for a new summary, from the result it is made on, so the
 * editor opens on a sentence that works rather than an empty box.
 */
export function starterTemplate(columns: Column[] = []): string {
  const numeric = find(columns, (column) => column.type === "integer" || column.type === "float");
  if (numeric) {
    return `Total ${numeric.name} is {{ sum(${numeric.name}) }} across {{ count() }} rows.`;
  }
  return "{{ count() }} rows.";
}
