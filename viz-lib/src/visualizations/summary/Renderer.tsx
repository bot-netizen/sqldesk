import React, { useMemo } from "react";
import { GLYPHS, Piece, render } from "./template";
import "./render.less";

/*
  The summary, drawn: words, and the query's values in them, each coloured by
  the first rule that holds for it.

  Three layouts from the one template. A sentence keeps the template's own
  line breaks; bullets make each line a point; a status line joins the lines
  with a dot, for a strip across the top of a page.
*/

function Value({ piece }: { piece: Piece }) {
  if (piece.kind === "problem") {
    // Said in place, where the value would have been: a blank is how a
    // broken summary goes unnoticed for a month.
    return (
      <span className="summary-problem" title={piece.expression} data-test="Summary.Problem">
        {piece.text}
      </span>
    );
  }
  if (piece.kind === "value") {
    return (
      <span className={`summary-value summary-value--${piece.tone || "plain"}`} data-test="Summary.Value">
        {piece.icon && GLYPHS[piece.icon] ? (
          <span className="summary-icon" aria-hidden="true">
            {GLYPHS[piece.icon]}
          </span>
        ) : null}
        {piece.text}
      </span>
    );
  }
  return <>{piece.text}</>;
}

/** The pieces, cut into lines at the template's own line breaks. */
export function toLines(pieces: Piece[]): Piece[][] {
  const lines: Piece[][] = [[]];
  pieces.forEach((piece) => {
    if (piece.kind !== "text") {
      lines[lines.length - 1].push(piece);
      return;
    }
    piece.text.split("\n").forEach((part, index) => {
      if (index > 0) {
        lines.push([]);
      }
      if (part) {
        lines[lines.length - 1].push({ kind: "text", text: part });
      }
    });
  });
  return lines.filter((line) => line.some((piece) => piece.kind !== "text" || piece.text.trim()));
}

export default function Renderer({ data, options }: any) {
  const pieces = useMemo(
    () => render(options.template || "", data || {}, options.rules || []),
    [options.template, options.rules, data]
  );

  if (!(options.template || "").trim()) {
    return (
      <div className="summary-visualization summary-empty" data-test="Summary.Empty">
        Write the summary in the editor: words, with values like {"{{ sum(revenue) }}"} in them.
      </div>
    );
  }

  const layout = options.layout || "sentence";
  if (layout === "sentence") {
    return (
      <div className="summary-visualization summary--sentence" data-test="Summary">
        {pieces.map((piece, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <Value key={index} piece={piece} />
        ))}
      </div>
    );
  }

  const lines = toLines(pieces);
  if (layout === "bullets") {
    return (
      <ul className="summary-visualization summary--bullets" data-test="Summary">
        {lines.map((line, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <li key={index}>
            {line.map((piece, at) => (
              // eslint-disable-next-line react/no-array-index-key
              <Value key={at} piece={piece} />
            ))}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="summary-visualization summary--status" data-test="Summary">
      {lines.map((line, index) => (
        // eslint-disable-next-line react/no-array-index-key
        <React.Fragment key={index}>
          {index > 0 && (
            <span className="summary-separator" aria-hidden="true">
              ·
            </span>
          )}
          <span className="summary-status-item">
            {line.map((piece, at) => (
              // eslint-disable-next-line react/no-array-index-key
              <Value key={at} piece={piece} />
            ))}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
}
