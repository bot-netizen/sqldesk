# sql-formatter (vendored)

`sql-formatter` 2.3.3 by ZeroTurnaround, MIT licensed — the licence is in
`LICENSE` beside this file.

**It is not stock.** The copy carries one modification: `core/Tokenizer.js`
treats `{{ param }}`, `${param}` and `r'...'` as single tokens, so that
formatting a query does not tear its parameter placeholders apart. Those
patterns are requested in `languages/StandardSqlFormatter.js`. There is a test
for it in `client/app/lib/queryFormat.test.js`, and it is the reason this is
vendored rather than installed.

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
