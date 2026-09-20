import { isEqual } from "lodash";
import React, { useEffect, useRef, Suspense } from "react";
import ErrorBoundary, { ErrorMessage } from "@/components/ErrorBoundary";
import { RendererPropTypes } from "@/visualizations/prop-types";
import registeredVisualizations from "@/visualizations/registeredVisualizations";
import lazyVisualizationComponent from "@/visualizations/lazyComponents";

/*
(ts-migrate) TODO: Migrate the remaining prop types
...RendererPropTypes
*/
type Props = {
  type: string;
  addonBefore?: React.ReactNode;
  addonAfter?: React.ReactNode;
} & typeof RendererPropTypes;

export default function Renderer({
  type,
  data,
  options: optionsProp,
  visualizationName,
  addonBefore,
  addonAfter,
  ...otherProps
}: Props) {
  const lastOptions = useRef();
  const errorHandlerRef = useRef();

  // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
  const { getOptions } = registeredVisualizations[type];
  // Fetched the first time this type is drawn; instant every time after.
  const Renderer = lazyVisualizationComponent(type, "Renderer");

  // Avoid unnecessary updates (which may be expensive or cause issues with
  // internal state of some visualizations like Table) - compare options deeply
  // and use saved reference if nothing changed
  let options = getOptions(optionsProp, data);
  if (isEqual(lastOptions.current, options)) {
    options = lastOptions.current;
  }
  lastOptions.current = options;

  useEffect(() => {
    if (errorHandlerRef.current) {
      // @ts-expect-error ts-migrate(2532) FIXME: Object is possibly 'undefined'.
      errorHandlerRef.current.reset();
    }
  }, [optionsProp, data]);

  return (
    <div className="visualization-renderer">
      {addonBefore}
      {/* @ts-expect-error ts-migrate(2769) FIXME: No overload matches this call. */}
      <ErrorBoundary
        ref={errorHandlerRef}
        renderError={() => <ErrorMessage>Error while rendering visualization.</ErrorMessage>}
      >
        <div className="visualization-renderer-wrapper">
          {/* Blank rather than a spinner: the wait is a chunk fetch, usually
              already finished by the time the query result arrives, and a
              second spinner next to the widget's own only flickers. */}
          <Suspense fallback={<div className="visualization-renderer-loading" />}>
            <Renderer options={options} data={data} visualizationName={visualizationName} {...otherProps} />
          </Suspense>
        </div>
      </ErrorBoundary>
      {addonAfter}
    </div>
  );
}
