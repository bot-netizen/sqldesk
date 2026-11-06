import { Query } from "@/services/query";
import * as queryFormat from "./queryFormat";

describe("QueryFormat.formatQuery", () => {
  test("returns same query text when syntax is not supported", () => {
    const unsupportedSyntax = "unsupported-syntax";
    const queryText = "select * from example";
    const isFormatQueryAvailable = queryFormat.isFormatQueryAvailable(unsupportedSyntax);
    const formattedQuery = queryFormat.formatQuery(queryText, unsupportedSyntax);

    expect(isFormatQueryAvailable).toBeFalsy();
    expect(formattedQuery).toBe(queryText);
  });

  describe("sql", () => {
    const syntax = "sql";

    test("returns the formatted query text", () => {
      const queryText = "select column1, column2 from example where column1 = 2";
      const expectedFormattedQueryText = [
        "select",
        "  column1,",
        "  column2",
        "from",
        "  example",
        "where",
        "  column1 = 2",
      ].join("\n");
      const isFormatQueryAvailable = queryFormat.isFormatQueryAvailable(syntax);
      const formattedQueryText = queryFormat.formatQuery(queryText, syntax);
      expect(isFormatQueryAvailable).toBeTruthy();
      expect(formattedQueryText).toBe(expectedFormattedQueryText);
    });

    /*
      `1e-12` came back as `1e -12`, which is a syntax error.

      The tokenizer had no rule for an exponent, so it read the word `1e`,
      then a minus, then `12` -- and the formatter spaces out a binary
      operator. Only a *signed* exponent produced it, which is why `3e10`
      worked and nobody noticed.
    */
    test("leaves scientific notation alone", () => {
      expect(queryFormat.formatQuery("select 1e-12", syntax)).toBe("select\n  1e-12");
      expect(queryFormat.formatQuery("select 2.5e+8", syntax)).toBe("select\n  2.5e+8");
      expect(queryFormat.formatQuery("select 1E-12", syntax)).toBe("select\n  1E-12");
      expect(queryFormat.formatQuery("select 3e10", syntax)).toBe("select\n  3e10");
    });

    test("and still spaces out subtraction, which looks the same to a lexer", () => {
      // The risk in teaching it about exponents is that it stops seeing a
      // minus where there really is one.
      expect(queryFormat.formatQuery("select a-12 from t", syntax)).toBe("select\n  a -12\nfrom\n  t");
      expect(queryFormat.formatQuery("select 5-2", syntax)).toBe("select\n  5 -2");
    });

    test("still recognizes parameters after formatting", () => {
      const queryText = "select {{param1}}, {{ param2 }}, {{ date-range.start }} from example";
      const formattedQueryText = queryFormat.formatQuery(queryText, syntax);
      const queryParameters = new Query({ query: queryText }).getParameters().parseQuery();
      const formattedQueryParameters = new Query({ query: formattedQueryText }).getParameters().parseQuery();
      expect(formattedQueryParameters.sort()).toEqual(queryParameters.sort());
    });
  });

  describe("json", () => {
    const syntax = "json";

    test("returns the formatted query text", () => {
      const queryText = '{"collection": "example","limit": 10}';
      const expectedFormattedQueryText = '{\n    "collection": "example",\n    "limit": 10\n}';
      const isFormatQueryAvailable = queryFormat.isFormatQueryAvailable(syntax);
      const formattedQueryText = queryFormat.formatQuery(queryText, syntax);
      expect(isFormatQueryAvailable).toBeTruthy();
      expect(formattedQueryText).toBe(expectedFormattedQueryText);
    });
  });
});
