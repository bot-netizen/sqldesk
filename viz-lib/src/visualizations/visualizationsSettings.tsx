import React from "react";
import { extend, isString } from "lodash";
import Tooltip from "antd/lib/tooltip";
import { setNumberSeparators } from "./shared/valueOptions";

type HelpTriggerProps = {
  title?: React.ReactNode;
  href: string;
  className?: string;
  children?: React.ReactNode;
};

function HelpTrigger({ title, href, className, children }: HelpTriggerProps) {
  return (
    <Tooltip
      title={
        <React.Fragment>
          {title}
          <i className="fa fa-external-link" style={{ marginLeft: 5 }} />
        </React.Fragment>
      }
    >
      <a className={className} href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    </Tooltip>
  );
}

HelpTrigger.defaultValues = {
  title: null,
  className: null,
  children: null,
};

function Link(props: any) {
  return <a {...props} />;
}

const DEFAULT_THOUSANDS_SEPARATOR = ",";
const DEFAULT_DECIMAL_SEPARATOR = ".";

export const visualizationsSettings = {
  HelpTriggerComponent: HelpTrigger,
  LinkComponent: Link,
  dateFormat: "DD/MM/YYYY",
  dateTimeFormat: "DD/MM/YYYY HH:mm",
  integerFormat: "0,0",
  floatFormat: "0,0.00",
  thousandsSeparator: DEFAULT_THOUSANDS_SEPARATOR,
  decimalSeparator: DEFAULT_DECIMAL_SEPARATOR,
  nullValue: "null",
  booleanValues: ["false", "true"],
  tableCellMaxJSONSize: 50000,
  choroplethAvailableMaps: {},
};

export function updateVisualizationsSettings(options: any) {
  extend(visualizationsSettings, options);

  // The organization's separators (Settings > General > Format). They are
  // pushed into the formatter rather than read from here, so that file goes
  // on depending on nothing. Each falls back to its default when it is not a
  // string, so a bad value never leaves the formatter stuck on a stale one.
  const { thousandsSeparator, decimalSeparator } = visualizationsSettings;
  setNumberSeparators(
    isString(thousandsSeparator) ? thousandsSeparator : DEFAULT_THOUSANDS_SEPARATOR,
    isString(decimalSeparator) ? decimalSeparator : DEFAULT_DECIMAL_SEPARATOR
  );
}
