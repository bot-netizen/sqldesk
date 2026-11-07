import getOptions from "./getOptions";
import { whatIsMissing } from "./prepareData";

/*
  A cohort over a result without the columns it reads was a blank white box.
  Found on the demo's own cohort -- its query names the columns cohort_date
  and week_number, the cohort's defaults are date and day_number -- which
  was blank on the dashboard built to show every visualization working.
*/

const columns = ["cohort_date", "week_number", "value", "total"].map((name) => ({ name }));
const rows = [{ cohort_date: "2026-08-10", week_number: 0, value: 40, total: 40 }];

describe("Visualizations -> Cohort -> what is missing", () => {
  test("columns named otherwise are named in the message, with where to fix it", () => {
    const problem = whatIsMissing({ columns, rows }, getOptions({}));
    expect(problem).toContain("“date”");
    expect(problem).toContain("“day_number”");
    expect(problem).toContain("under Columns");
    // The two it can find are not complained about.
    expect(problem).not.toContain("“total”");
    expect(problem).not.toContain("“value”");
  });

  test("told the columns, there is nothing to say", () => {
    const options = getOptions({ dateColumn: "cohort_date", stageColumn: "week_number" });
    expect(whatIsMissing({ columns, rows }, options)).toBeNull();
  });

  test("a result with no rows says so rather than drawing an empty table", () => {
    const options = getOptions({ dateColumn: "cohort_date", stageColumn: "week_number" });
    expect(whatIsMissing({ columns, rows: [] }, options)).toContain("no rows");
  });
});
