import React, { useState } from "react";
import classNames from "classnames";

import "./TypeLogo.less";

// A logo is a file named after the type: /static/images/db-logos/<type>.png. Add a
// type without adding its file -- which is what happened to Kafka, and would have
// happened to Mimir -- and every one of the ten places that draws one rendered the
// browser's broken-image glyph. Nothing logged it and nothing looked wrong in the
// code, because an <img> that 404s is not an error anybody is told about.
//
// So a missing file degrades to a tile with the type's initials instead. It also
// means a new data source type is complete the moment its runner is registered, and
// a real logo becomes a file drop rather than a release blocker.

// Chosen to sit beside the app's own palette and to stay legible under white text.
const TILE_COLOURS = ["#4b6cb7", "#2e8b7a", "#8a5fbf", "#b5651d", "#3c7d9e", "#9c4668", "#5c7a3f", "#7a5c3f"];

function tileColour(label: string): string {
  // Deterministic, so a type keeps the same colour between renders and reloads.
  let hash = 0;
  for (let i = 0; i < label.length; i += 1) {
    hash = (hash * 31 + label.charCodeAt(i)) % 100000;
  }
  return TILE_COLOURS[hash % TILE_COLOURS.length];
}

function initials(label: string): string {
  const words = label.replace(/[_-]+/g, " ").split(/\s+/).filter(Boolean);

  if (words.length === 0) {
    return "?";
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return (words[0][0] + words[1][0]).toUpperCase();
}

export interface TypeLogoProps {
  src?: string | null;
  // What the tile says when there is no file, and what the image is called.
  label: string;
  width?: number | string | null;
  height?: number | string | null;
  className?: string;
  alt?: string | null;
}

export default function TypeLogo({
  src = null,
  label,
  width = null,
  height = null,
  className = "",
  alt = null,
  ...props
}: TypeLogoProps) {
  const [brokenSrc, setBrokenSrc] = useState<string | null>(null);

  if (src && brokenSrc !== src) {
    return (
      <img
        {...props}
        src={src}
        width={width === null ? undefined : width}
        height={height === null ? undefined : height}
        className={className}
        alt={alt || label}
        onError={() => setBrokenSrc(src)}
      />
    );
  }

  // Sized inline only where the caller gave a size. Where it did not, the context's
  // own stylesheet sizes it -- CardsList does, at three breakpoints -- and an inline
  // width would beat the narrow ones.
  const size = height || width;
  const style: React.CSSProperties = { backgroundColor: tileColour(label) };
  if (size) {
    style.width = size;
    style.height = size;
    style.fontSize = Math.max(8, Math.round(Number(size) * 0.4));
  }

  return (
    <span
      {...props}
      className={classNames("type-logo-fallback", className)}
      style={style}
      title={label}
      aria-label={alt || label}
      role="img"
    >
      {initials(label)}
    </span>
  );
}
