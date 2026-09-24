import React from "react";
import Popover from "antd/lib/popover";
import QuestionCircleFilledIcon from "@ant-design/icons/QuestionCircleFilled";
import { visualizationsSettings } from "@/visualizations/visualizationsSettings";

import "./context-help.less";

type OwnContextHelpProps = {
  icon?: React.ReactNode;
  children?: React.ReactNode;
};

const contextHelpDefaultProps = {
  icon: null,
  children: null,
};

type ContextHelpProps = OwnContextHelpProps & typeof contextHelpDefaultProps;

export default function ContextHelp({ icon, children, ...props }: ContextHelpProps) {
  return (
    <Popover {...props} content={children}>
      {icon || ContextHelp.defaultIcon}
    </Popover>
  );
}

ContextHelp.defaultProps = contextHelpDefaultProps;

ContextHelp.defaultIcon = <QuestionCircleFilledIcon className="context-help-default-icon" />;

function DateTimeFormatSpecs() {
  const { HelpTriggerComponent } = visualizationsSettings;
  return (
    <HelpTriggerComponent
      title="Formatting Dates and Times"
      href="https://momentjs.com/docs/#/displaying/format/"
      className="visualization-editor-context-help"
    >
      {ContextHelp.defaultIcon}
    </HelpTriggerComponent>
  );
}

function TickFormatSpecs() {
  const { HelpTriggerComponent } = visualizationsSettings;
  return (
    <HelpTriggerComponent
      title="Tick Formatting"
      href="https://sqldesk.github.io/sqldesk"
      className="visualization-editor-context-help"
    >
      {ContextHelp.defaultIcon}
    </HelpTriggerComponent>
  );
}

ContextHelp.DateTimeFormatSpecs = DateTimeFormatSpecs;
ContextHelp.TickFormatSpecs = TickFormatSpecs;
