import React from "react";
import cx from "classnames";

import "./Section.less";

// Both of these used to declare their props as `OwnProps & typeof defaults`,
// where `defaults` was `{ className: null, children: null }`. TypeScript
// infers that object's type literally, so the intersection narrowed
// `children` to `React.ReactNode & null` -- that is, `null` -- and every
// `<Section>` with anything inside it became an error. That is where the
// hundred or so "Section's children type is too narrow" suppressions across
// the visualization editors came from. The defaults themselves did nothing:
// `cx` ignores an absent class, and an absent child renders nothing.

type SectionTitleProps = {
  className?: string;
  children?: React.ReactNode;
};

function SectionTitle({ className, children, ...props }: SectionTitleProps) {
  if (!children) {
    return null;
  }

  return (
    <h4 className={cx("visualization-editor-section-title", className)} {...props}>
      {children}
    </h4>
  );
}

type SectionProps = {
  className?: string;
  children?: React.ReactNode;
};

export default function Section({ className, children, ...props }: SectionProps) {
  return (
    <div className={cx("visualization-editor-section", className)} {...props}>
      {children}
    </div>
  );
}

Section.Title = SectionTitle;
