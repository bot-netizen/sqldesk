import React from "react";
import { Section, Select, Input, InputNumber } from "@/components/visualizations/editor";
import { VALUE_STYLES, ValueFormat, normalizeValueFormat, formatValue } from "../format";

type Props = {
  format?: Partial<ValueFormat> | null;
  onChange: (format: ValueFormat) => void;
  /** Shown beside the controls so the effect is visible while editing. */
  sampleValue?: unknown;
  testPrefix: string;
};

function toDecimals(value: any): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(20, Math.round(n))) : null;
}

export default function ValueFormatSection({ format, onChange, sampleValue, testPrefix }: Props) {
  const f = normalizeValueFormat(format);
  const update = (changes: Partial<ValueFormat>) => onChange({ ...f, ...changes });

  return (
    <React.Fragment>
      <Section>
        <Select
          layout="horizontal"
          label="Format"
          value={f.style}
          data-test={`${testPrefix}.Style`}
          onChange={(style: any) => update({ style })}
        >
          {VALUE_STYLES.map((s) => (
            <Select.Option key={s.value} value={s.value} data-test={`${testPrefix}.Style.${s.value}`}>
              {s.label} <span className="value-options-example">{s.example}</span>
            </Select.Option>
          ))}
        </Select>
      </Section>

      {f.style === "currency" && (
        <Section>
          <Input
            layout="horizontal"
            label="Currency code"
            placeholder="USD"
            value={f.currency}
            maxLength={3}
            data-test={`${testPrefix}.Currency`}
            onChange={(e: any) => update({ currency: String(e.target.value || "").toUpperCase() })}
          />
        </Section>
      )}

      <Section>
        <InputNumber
          layout="horizontal"
          label="Decimal places"
          placeholder="Automatic"
          min={0}
          max={20}
          value={f.decimals === null ? undefined : f.decimals}
          data-test={`${testPrefix}.Decimals`}
          onChange={(v: any) => update({ decimals: toDecimals(v) })}
        />
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Prefix"
          value={f.prefix}
          data-test={`${testPrefix}.Prefix`}
          onChange={(e: any) => update({ prefix: e.target.value })}
        />
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Suffix"
          placeholder="e.g. ms, req/s"
          value={f.suffix}
          data-test={`${testPrefix}.Suffix`}
          onChange={(e: any) => update({ suffix: e.target.value })}
        />
      </Section>

      {sampleValue !== undefined && sampleValue !== null && (
        <p className="value-options-preview" data-test={`${testPrefix}.Preview`}>
          Shows as <strong>{formatValue(sampleValue, f)}</strong>
        </p>
      )}
    </React.Fragment>
  );
}
