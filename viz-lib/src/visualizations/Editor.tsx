import React, { useMemo, Suspense } from "react";
import { EditorPropTypes } from "@/visualizations/prop-types";
import registeredVisualizations from "@/visualizations/registeredVisualizations";
import lazyVisualizationComponent from "@/visualizations/lazyComponents";

/*
(ts-migrate) TODO: Migrate the remaining prop types
...EditorPropTypes
*/
type Props = {
  type: string;
} & typeof EditorPropTypes;

export default function Editor({ type, options: optionsProp, data, ...otherProps }: Props) {
  // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
  const { getOptions } = registeredVisualizations[type];
  // Fetched the first time this type is edited; instant every time after.
  const Editor = lazyVisualizationComponent(type, "Editor");
  const options = useMemo(() => getOptions(optionsProp, data), [optionsProp, data]);

  return (
    <Suspense fallback={<div className="visualization-editor-loading" />}>
      <Editor options={options} data={data} {...otherProps} />
    </Suspense>
  );
}
