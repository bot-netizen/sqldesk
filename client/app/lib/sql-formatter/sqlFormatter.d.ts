// Types for the vendored sql-formatter. Kept beside the source rather than
// patched into it, so the vendored copy stays byte-identical to what it was
// taken from and can be diffed against upstream.

export interface SqlFormatterConfig {
  /** Standard SQL unless one of the dialects below is named. */
  language?: "sql" | "db2" | "n1ql" | "pl/sql";
  /** Characters used for one level of indentation. Two spaces by default. */
  indent?: string;
  /** Values substituted for placeholders while formatting. */
  params?: { [name: string]: string } | string[];
}

declare const sqlFormatter: {
  format(query: string, cfg?: SqlFormatterConfig): string;
};

export default sqlFormatter;
