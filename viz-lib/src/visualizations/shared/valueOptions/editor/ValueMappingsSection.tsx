import React from "react";
import Button from "antd/lib/button";
import AntInput from "antd/lib/input";
import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import DeleteOutlinedIcon from "@ant-design/icons/DeleteOutlined";
import { Section, ControlLabel } from "@/components/visualizations/editor";
import { ValueMapping } from "../mappings";
import ColorSelect from "./ColorSelect";

type Props = {
  mappings?: Partial<ValueMapping>[] | null;
  onChange: (mappings: ValueMapping[]) => void;
  testPrefix: string;
  description?: React.ReactNode;
};

export default function ValueMappingsSection({ mappings, onChange, testPrefix, description }: Props) {
  const rows: ValueMapping[] = (Array.isArray(mappings) ? mappings : []).map((m) => ({
    value: (m && m.value) || "",
    text: (m && m.text) || "",
    color: (m && m.color) || "",
  }));
  const update = (i: number, changes: Partial<ValueMapping>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...changes } : r)));

  return (
    <Section>
      <ControlLabel label="Value mappings">
        {description && <p className="value-options-help">{description}</p>}
        <div className="value-options-rows" data-test={`${testPrefix}.Mappings`}>
          {rows.map((row, i) => (
            <div className="value-options-row" key={i} data-test={`${testPrefix}.Mappings.${i}`}>
              <AntInput
                placeholder="Value"
                value={row.value}
                aria-label={`Mapping ${i + 1} value`}
                data-test={`${testPrefix}.Mappings.${i}.Value`}
                onChange={(e: any) => update(i, { value: e.target.value })}
              />
              <span className="value-options-row-label" aria-hidden="true">
                →
              </span>
              <AntInput
                placeholder="Show as"
                value={row.text}
                aria-label={`Mapping ${i + 1} text`}
                data-test={`${testPrefix}.Mappings.${i}.Text`}
                onChange={(e: any) => update(i, { text: e.target.value })}
              />
              <ColorSelect
                allowNone
                value={row.color}
                onChange={(color) => update(i, { color })}
                data-test={`${testPrefix}.Mappings.${i}.Color`}
                aria-label={`Mapping ${i + 1} colour`}
              />
              <Button
                type="link"
                aria-label={`Remove mapping ${i + 1}`}
                data-test={`${testPrefix}.Mappings.${i}.Remove`}
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
              >
                <DeleteOutlinedIcon />
              </Button>
            </div>
          ))}
        </div>
        <Button
          className="value-options-add"
          onClick={() => onChange([...rows, { value: "", text: "", color: "critical" }])}
          data-test={`${testPrefix}.Mappings.Add`}
        >
          <PlusOutlinedIcon /> Add mapping
        </Button>
      </ControlLabel>
    </Section>
  );
}
