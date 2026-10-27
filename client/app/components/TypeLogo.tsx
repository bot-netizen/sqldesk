import React, { useState } from "react";
import classNames from "classnames";

import isMissingLogo from "@/lib/logoAssets";
// Shared with the avatar: one definition of "a colour from a name".
import { initials, tileColour } from "@/lib/initialsTile";

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
//
// Degrading on `onError` still means asking for the file and waiting for the 404,
// which is a failed request logged on every page that lists the type. Where the
// build can tell us the file is not there, we go straight to the tile instead and
// never ask -- `onError` stays for the ones nobody could know about in advance.

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

  if (src && brokenSrc !== src && !isMissingLogo(src)) {
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
