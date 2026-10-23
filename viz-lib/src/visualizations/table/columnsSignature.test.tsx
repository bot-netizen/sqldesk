import { columnsSignature } from "./Renderer";

// The sort reset whenever the column arrays were new objects -- which they are
// on every result -- so a live table lost its order on every refresh.
describe("when a table's sort is reset", () => {
  const configured = [{ name: "region" }, { name: "amount" }];

  test("not for a new result with the same columns", () => {
    expect(columnsSignature(configured, [{ name: "region" }, { name: "amount" }])).toEqual(
      columnsSignature([...configured], [{ name: "region" }, { name: "amount" }])
    );
  });

  test("but when the columns change", () => {
    expect(columnsSignature(configured, [{ name: "region" }])).not.toEqual(
      columnsSignature(configured, [{ name: "region" }, { name: "amount" }])
    );
  });
});
