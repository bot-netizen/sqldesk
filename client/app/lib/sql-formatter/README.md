# sql-formatter (vendored)

`sql-formatter` 2.3.3 by ZeroTurnaround, MIT licensed — the licence is in
`LICENSE` beside this file.

**It is not stock.** The copy carries two modifications, both in
`core/Tokenizer.js`, and both are the reason this is vendored rather than
installed. There are tests for each in `client/app/lib/queryFormat.test.js`.

1. **Parameters stay whole.** `{{ param }}`, `${param}` and `r'...'` are
   single tokens, so formatting a query does not tear its placeholders apart.
   Those patterns are requested in `languages/StandardSqlFormatter.js`.

2. **Numbers may carry an exponent.** `NUMBER_REGEX` accepts `1e-12` and
   `2.5e+8`. Stock, the tokenizer reads `1e` as a word, then a minus, then
   `12` -- and the formatter spaces out what it takes to be a binary
   operator, so `1e-12` comes back as `1e -12`, which is a syntax error. Only
   a *signed* exponent does this, which is why `3e10` was fine and the fault
   went unnoticed.

It was previously pulled from a git tarball in another organisation's GitHub
account, which would have broken every install the day that repository moved or
went private.

## Before upgrading it

The published `sql-formatter` on npm is at 15.x. That is a different API, a
different module shape and different output — upgrading reformats every saved
query, and unless the placeholder handling above is carried across it will also
break parameters. It is a decision to take deliberately, with the test above
green, rather than a version bump.

Only `format()` is used, from `client/app/lib/queryFormat.ts`.
