import { describeCronProblem } from "./CronScheduleDialog";

// This mirrors croniter, which is the authority -- the server rejects anything
// it cannot read. These cases are the ones somebody is likely to type, so they
// are told before a round trip rather than after one.
describe("describeCronProblem", () => {
  const accepts = (expression) => expect(describeCronProblem(expression)).toBeNull();
  const rejects = (expression) => expect(describeCronProblem(expression)).toEqual(expect.any(String));

  it("accepts the shapes a crontab line takes", () => {
    accepts("* * * * *");
    accepts("0 5 * * *");
    accepts("*/15 * * * *");
    accepts("0 9 * * 1-5");
    accepts("30 3 1 * *");
    accepts("0,30 * * * *");
    accepts("0 0-6/2 * * *");
    accepts("0 9 * jan-mar mon");
    accepts("  0 5 * * *  ");
  });

  it("accepts 7 as Sunday", () => {
    // Both 0 and 7 mean Sunday; rejecting 7 would refuse a line copied from a
    // working crontab.
    accepts("0 9 * * 7");
  });

  it("counts the fields", () => {
    expect(describeCronProblem("0 5 * *")).toContain("five fields");
    expect(describeCronProblem("0 5 * * * *")).toContain("five fields");
  });

  it("names the field that is wrong", () => {
    expect(describeCronProblem("99 5 * * *")).toContain("minute");
    expect(describeCronProblem("0 99 * * *")).toContain("hour");
    expect(describeCronProblem("0 5 99 * *")).toContain("day of the month");
    expect(describeCronProblem("0 5 * 99 *")).toContain("month");
    expect(describeCronProblem("0 5 * * 9")).toContain("day of the week");
  });

  it("rejects what is not a schedule at all", () => {
    rejects("");
    rejects("   ");
    rejects("every day at 9");
    rejects(null);
    rejects(undefined);
  });

  it("rejects malformed steps and ranges", () => {
    rejects("*/ * * * *");
    rejects("*/0 * * * *");
    rejects("1-2-3 * * * *");
    rejects("0,, * * * *");
  });
});
