import React from "react";
import { Section, Select, Input, InputNumber, Checkbox } from "@/components/visualizations/editor";
import { VALUE_STYLES, ValueFormat, normalizeValueFormat, formatValue } from "../format";

type Props = {
  format?: Partial<ValueFormat> | null;
  onChange: (format: ValueFormat) => void;
  /** Shown beside the controls so the effect is visible while editing. */
  sampleValue?: unknown;
  /** For editors with more than one of these: "Numbers", "Percentages". */
  title?: React.ReactNode;
  testPrefix: string;
};

function toDecimals(value: any): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(20, Math.round(n))) : null;
}

export default function ValueFormatSection({ format, onChange, sampleValue, title, testPrefix }: Props) {
  const f = normalizeValueFormat(format);
  const update = (changes: Partial<ValueFormat>) => onChange({ ...f, ...changes });

  return (
    <React.Fragment>
      {title && (
        <Section>
          <h4 className="value-options-heading">{title}</h4>
        </Section>
      )}
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

      {f.decimals !== null && f.decimals > 0 && (
        <Section>
          <Select
            layout="horizontal"
            label="Trailing zeros"
            value={f.hideZeroFraction ? "whole" : f.minDecimals === 0 ? "needed" : "always"}
            data-test={`${testPrefix}.TrailingZeros`}
            onChange={(mode: any) =>
              update({
                minDecimals: mode === "needed" ? 0 : null,
                hideZeroFraction: mode === "whole",
              })
            }
          >
            <Select.Option value="always" data-test={`${testPrefix}.TrailingZeros.always`}>
              Always <span className="value-options-example">3.00</span>
            </Select.Option>
            <Select.Option value="needed" data-test={`${testPrefix}.TrailingZeros.needed`}>
              Only when needed <span className="value-options-example">3, 3.5</span>
            </Select.Option>
            <Select.Option value="whole" data-test={`${testPrefix}.TrailingZeros.whole`}>
              Not on whole numbers <span className="value-options-example">3, 3.50</span>
            </Select.Option>
          </Select>
        </Section>
      )}

      <Section>
        <Checkbox
          data-test={`${testPrefix}.Grouping`}
          checked={f.grouping !== false}
          onChange={(event: any) => update({ grouping: event.target.checked })}
        >
          Group thousands
        </Checkbox>
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
