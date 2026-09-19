import React from "react";
import { Select } from "@/components/visualizations/editor";
import { ColumnLike } from "./rows";

/*
  A column picker, the one piece every value visualization's editor repeats.
*/

type ColumnSelectProps = {
  label: string;
  value: string;
  columns: ColumnLike[];
  onChange: (column: string) => void;
  /** Offer "none" as the first choice, with this text. */
  noneLabel?: string;
  "data-test": string;
};

export function ColumnSelect({ label, value, columns, onChange, noneLabel, ...rest }: ColumnSelectProps) {
  return (
    <Select
      layout="horizontal"
      label={label}
      value={value || ""}
      data-test={rest["data-test"]}
      onChange={(v: any) => onChange(String(v || ""))}
    >
      {noneLabel !== undefined && (
        // @ts-expect-error Select.Option is added by withControlLabel's wrapped component
        <Select.Option key="" value="">
          {noneLabel}
          {/* @ts-expect-error see above */}
        </Select.Option>
      )}
      {columns.map((c) => (
        // @ts-expect-error Select.Option is added by withControlLabel's wrapped component
        <Select.Option key={c.name} value={c.name} data-test={`${rest["data-test"]}.${c.name}`}>
          {c.name}
          {/* @ts-expect-error see above */}
        </Select.Option>
      ))}
    </Select>
  );
}
