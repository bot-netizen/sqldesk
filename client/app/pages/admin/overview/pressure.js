/*
  Reading a limit.

  The numbers the overview shows are only useful as fractions of something:
  38 Postgres connections means nothing, 38 of 100 means something, and 92 of
  100 means stop reading and go and do something. So every limit goes through
  here and comes back with a level, and the page colours it rather than
  deciding for itself.

  Kept apart from the drawing because it is the part that can be wrong in a
  way nobody notices: a bar is obviously missing, a threshold quietly off by a
  factor of ten is not.
*/

export const OK = "ok";
export const WATCH = "watch";
export const CRITICAL = "critical";
/** Nothing to measure against -- Redis with no maxmemory, say. */
export const UNKNOWN = "unknown";

const WATCH_AT = 0.75;
const CRITICAL_AT = 0.9;

/**
 * How close `used` is to `limit`, as a level and a fraction.
 *
 * A missing limit is not a limit of zero: Redis reports maxmemory as 0 when
 * none is set, which means "as much as the machine has", not "none". Saying
 * 100% there would have every install permanently on fire.
 */
export function pressure(used, limit) {
  if (!Number.isFinite(used) || !Number.isFinite(limit) || limit <= 0) {
    return { level: UNKNOWN, fraction: null };
  }

  const fraction = used / limit;
  let level = OK;
  if (fraction >= CRITICAL_AT) {
    level = CRITICAL;
  } else if (fraction >= WATCH_AT) {
    level = WATCH;
  }

  return { level, fraction };
}

const UNITS = ["B", "kB", "MB", "GB", "TB"];

/** Bytes, at the size a person would say them. */
export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "—";
  }
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  // No decimal on bytes: "512.0 B" is a strange thing to read.
  return `${unit === 0 ? value : value.toFixed(1)} ${UNITS[unit]}`;
}

/**
 * How long something has been running, at the precision that matters.
 *
 * Seconds up to a minute, because the difference between 3s and 40s is the
 * whole question; minutes after that, because the difference between 61 and
 * 62 minutes is not.
 */
export function formatElapsed(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  if (seconds < 60) {
    return `${Math.floor(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ${Math.floor(seconds % 60)}s`;
  }
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** A ratio as a percentage, or a dash when there is nothing to divide. */
export function formatRatio(ratio) {
  if (!Number.isFinite(ratio)) {
    return "—";
  }
  return `${Math.round(ratio * 100)}%`;
}
