import React, { useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";

/*
  A picture a Python cell ended on.

  Two kinds, and the difference is the whole design.

  **A PNG** -- matplotlib, seaborn, `df.plot()` -- is drawn by an <img>. It
  is already a raster image and there is nothing a chart library could add.
  It costs the bundle nothing.

  **A Plotly spec** is rendered by plotly.js, which is ~1MB over the wire and
  is therefore imported *here, on demand*. This fork moved off Plotly to
  ECharts on purpose; bringing it back as a page-load cost for everybody
  would undo that. Loaded this way, only somebody who opens a notebook that
  actually shows a Plotly figure ever downloads it -- and then it is cached
  for the rest of their session.
*/
export default function CellFigure({ figure }) {
  if (!figure) {
    return null;
  }
  if (figure.kind === "png") {
    return (
      <div className="notebook-cell-figure" data-test="CellFigure">
        <img src={`data:image/png;base64,${figure.data}`} alt="This cell's figure" />
      </div>
    );
  }
  if (figure.kind === "plotly") {
    return <PlotlyFigure spec={figure.spec} />;
  }
  return (
    <Alert
      className="notebook-cell-notice"
      type="warning"
      showIcon
      message="This cell produced a picture this version cannot draw."
      data-test="CellFigureUnknown"
    />
  );
}

CellFigure.propTypes = { figure: PropTypes.object };
CellFigure.defaultProps = { figure: null };

export function PlotlyFigure({ spec }) {
  const holder = useRef(null);
  const [failed, setFailed] = useState(null);

  useEffect(() => {
    let live = true;
    // The dynamic import is the point: webpack puts plotly in a chunk of its
    // own, fetched the first time a notebook actually shows one of these.
    import(/* webpackChunkName: "plotly" */ "plotly.js-dist-min")
      .then((loaded) => {
        if (!live || !holder.current) {
          return;
        }
        const plotly = loaded.default || loaded;
        const figure = typeof spec === "string" ? JSON.parse(spec) : spec;
        plotly.newPlot(holder.current, figure.data || [], figure.layout || {}, {
          responsive: true,
          displaylogo: false,
        });
      })
      .catch(() => live && setFailed("That chart could not be drawn."));
    return () => {
      live = false;
    };
  }, [spec]);

  if (failed) {
    return <Alert className="notebook-cell-notice" type="error" showIcon message={failed} data-test="CellFigure" />;
  }
  return <div className="notebook-cell-figure" ref={holder} data-test="CellFigure" />;
}

PlotlyFigure.propTypes = { spec: PropTypes.oneOfType([PropTypes.string, PropTypes.object]).isRequired };
