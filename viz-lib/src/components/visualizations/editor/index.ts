import AntSelect from "antd/lib/select";
import AntInput from "antd/lib/input";
import AntInputNumber from "antd/lib/input-number";
import Checkbox from "antd/lib/checkbox";

import TealdashColorPicker from "@/components/ColorPicker";
import TealdashTextAlignmentSelect from "@/components/TextAlignmentSelect";

import withControlLabel, { ControlLabel } from "./withControlLabel";
import createTabbedEditor from "./createTabbedEditor";
import Section from "./Section";
import Switch from "./Switch";
import TextArea from "./TextArea";
import ContextHelp from "./ContextHelp";

export { Section, ControlLabel, Checkbox, Switch, TextArea, ContextHelp, withControlLabel, createTabbedEditor };
export const Select = withControlLabel(AntSelect);
export const Input = withControlLabel(AntInput);
export const InputNumber = withControlLabel(AntInputNumber);
export const ColorPicker = withControlLabel(TealdashColorPicker);
export const TextAlignmentSelect = withControlLabel(TealdashTextAlignmentSelect);
