import React from "react";
import AntSelect from "antd/lib/select";
import { SEMANTIC_COLORS, SEMANTIC_COLOR_NAMES, resolveColor } from "../colors";

// The chart series colours (tokens.less @series-1..8), offered after the
// meanings for the case where a colour is only a label, not a judgement.
export const SERIES_COLORS = ["#4a45b8", "#12a07a", "#d45d00", "#2e86c8", "#c04a86", "#8a6a16", "#1594ab", "#7b3fa0"];

function Swatch({ color }: { color: string }) {
  return <span className="value-options-swatch" style={{ background: resolveColor(color) }} aria-hidden="true" />;
}

type Props = {
  value: string;
  onChange: (color: string) => void;
  allowNone?: boolean;
  "data-test"?: string;
  "aria-label"?: string;
};

export default function ColorSelect({ value, onChange, allowNone = false, ...rest }: Props) {
  const known = SEMANTIC_COLOR_NAMES.includes(value as any) || SERIES_COLORS.includes(value);
  return (
    <AntSelect
      className="value-options-color-select"
      value={value || ""}
      onChange={(v: any) => onChange(String(v))}
      dropdownMatchSelectWidth={false}
      data-test={rest["data-test"]}
      aria-label={rest["aria-label"]}
    >
      {allowNone && (
        <AntSelect.Option value="">
          <span className="value-options-swatch-none" aria-hidden="true" /> None
        </AntSelect.Option>
      )}
      {SEMANTIC_COLOR_NAMES.map((name) => (
        <AntSelect.Option key={name} value={name} data-test={`${rest["data-test"]}.${name}`}>
          <Swatch color={name} /> {SEMANTIC_COLORS[name].label}
        </AntSelect.Option>
      ))}
      {SERIES_COLORS.map((hex, i) => (
        <AntSelect.Option key={hex} value={hex}>
          <Swatch color={hex} /> Series {i + 1}
        </AntSelect.Option>
      ))}
      {/* A colour saved some other way still shows, rather than reading as blank. */}
      {!known && value && (
        <AntSelect.Option key={value} value={value}>
          <Swatch color={value} /> {value}
        </AntSelect.Option>
      )}
    </AntSelect>
  );
}
