import React from "react";
import { asValueFormat, ValueFormat } from "@/visualizations/shared/valueOptions";
import { ValueFormatSection } from "@/visualizations/shared/valueOptions/editor";
import { createNumberFormatter } from "@/lib/value-format";

type Props = {
  column: {
    name: string;
    /** A numeral format string on a column saved before 0.5, else the shared format. */
    numberFormat?: string | Partial<ValueFormat>;
  };
  onChange: (...args: any[]) => any;
};

function Editor({ column, onChange }: Props) {
  return (
    <ValueFormatSection
      format={asValueFormat(column.numberFormat)}
      testPrefix="Table.ColumnEditor.Number.Format"
      onChange={(numberFormat) => onChange({ numberFormat })}
    />
  );
}

export default function initNumberColumn(column: any) {
  const format = createNumberFormatter(column.numberFormat, true);

  function prepareData(row: any) {
    return {
      text: format(row[column.name]),
    };
  }

  function NumberColumn({ row }: any) {
    // eslint-disable-line react/prop-types
    const { text } = prepareData(row);
    return text;
  }

  NumberColumn.prepareData = prepareData;

  return NumberColumn;
}

initNumberColumn.friendlyName = "Number";
initNumberColumn.Editor = Editor;
