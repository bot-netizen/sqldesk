import React, { useMemo } from "react";
import cx from "classnames";
import hoistNonReactStatics from "hoist-non-react-statics";
import * as Grid from "antd/lib/grid";
import Typography from "antd/lib/typography";

import "./control-label.less";

type OwnProps = {
  layout?: "vertical" | "horizontal";
  label?: React.ReactNode;
  labelProps?: any;
  disabled?: boolean;
  children?: React.ReactNode;
};

const controlLabelDefaultProps: OwnProps = {
  layout: "vertical",
  label: null,
  disabled: false,
  children: null,
};

// The defaults are typed as OwnProps rather than intersected in. Inferred,
// `children: null` narrowed the prop to exactly `null`, so passing a control
// to the thing whose whole job is to label a control was a type error -- which
// is why several callers carried a `@ts-expect-error` above them.
type Props = OwnProps;

export function ControlLabel({ layout, label, labelProps, disabled, children }: Props) {
  if (layout === "vertical" && label) {
    return (
      <div className="visualization-editor-control-label visualization-editor-control-label-vertical">
        <label {...labelProps}>
          <Typography.Text disabled={disabled}>{label}</Typography.Text>
        </label>
        {children}
      </div>
    );
  }

  if (layout === "horizontal" && label) {
    return (
      <Grid.Row
        className="visualization-editor-control-label visualization-editor-control-label-horizontal"
        // @ts-expect-error ts-migrate(2322) FIXME: Type '{ children: Element[]; className: string; ty... Remove this comment to see the full error message
        type="flex"
        align="middle"
        gutter={15}
      >
        <Grid.Col span={12}>
          <label {...labelProps}>
            <Typography.Text disabled={disabled}>{label}</Typography.Text>
          </label>
        </Grid.Col>
        <Grid.Col span={12}>{children}</Grid.Col>
      </Grid.Row>
    );
  }

  // No label to draw: the control stands on its own.
  return <React.Fragment>{children}</React.Fragment>;
}

ControlLabel.defaultProps = controlLabelDefaultProps;

/**
 * Everything the wrapped control carries besides being callable -- `Option`
 * and `OptGroup` on antd's Select, for instance. `hoistNonReactStatics` copies
 * these across at runtime, but the wrapper's own type knew nothing about them,
 * so every `<Select.Option>` in every editor needed a suppression. Omitting
 * the call signatures rather than intersecting the whole type keeps exactly
 * one signature for JSX to resolve.
 */
type Statics<C> = Omit<C, keyof CallableFunction>;

/** A control wrapped by `withControlLabel`, carrying `S` as static members. */
export type LabelledControl<S = unknown> = ((props: any) => JSX.Element) & S;

export default function withControlLabel<C>(WrappedControl: C): ((props: any) => JSX.Element) & Statics<C> {
  // eslint-disable-next-line react/prop-types
  function ControlWrapper({ className, id, layout, label, labelProps, disabled, ...props }: any) {
    const fallbackId = useMemo(() => `visualization-editor-control-${Math.random().toString(36).substr(2, 10)}`, []);
    labelProps = {
      ...labelProps,
      htmlFor: id || fallbackId,
    };

    return (
      <ControlLabel layout={layout} label={label} labelProps={labelProps} disabled={disabled}>
        {/* @ts-expect-error `C` is only known to be a component at the call site, not here */}
        <WrappedControl
          className={cx("visualization-editor-input", className)}
          id={labelProps.htmlFor}
          disabled={disabled}
          {...props}
        />
      </ControlLabel>
    );
  }

  // Copy static methods from `WrappedComponent`
  hoistNonReactStatics(ControlWrapper, WrappedControl as any);

  return ControlWrapper as ((props: any) => JSX.Element) & Statics<C>;
}
