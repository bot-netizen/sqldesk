import AntSelect from "antd/lib/select";
import AntInput from "antd/lib/input";
import AntInputNumber from "antd/lib/input-number";
import Checkbox from "antd/lib/checkbox";

import SQLDeskColorPicker from "@/components/ColorPicker";
import SQLDeskTextAlignmentSelect from "@/components/TextAlignmentSelect";

import React from "react";

import withControlLabel, { ControlLabel, LabelledControl } from "./withControlLabel";
import createTabbedEditor from "./createTabbedEditor";
import Section from "./Section";
import Switch from "./Switch";
import TextArea from "./TextArea";
import ContextHelp from "./ContextHelp";

export { Section, ControlLabel, Checkbox, Switch, TextArea, ContextHelp, withControlLabel, createTabbedEditor };
// Spelled out rather than inferred: antd's Option and OptGroup come from deep
// inside rc-select, which a generated declaration file cannot name portably.
export const Select: LabelledControl<{
  Option: React.ComponentType<any>;
  OptGroup: React.ComponentType<any>;
}> = withControlLabel(AntSelect);
export const Input = withControlLabel(AntInput);
export const InputNumber = withControlLabel(AntInputNumber);
export const ColorPicker = withControlLabel(SQLDeskColorPicker);
export const TextAlignmentSelect = withControlLabel(SQLDeskTextAlignmentSelect);
