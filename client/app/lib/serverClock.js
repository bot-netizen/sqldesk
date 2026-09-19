import moment from "moment";

/*
  The server's clock, as far as this tab can tell. Times the server wrote --
  when a result was retrieved -- are compared with it rather than with the
  browser's clock, which can be minutes out and would make a countdown to the
  next refresh say nonsense.
*/

let offsetMs = 0;

export function syncServerClock(serverTime, receivedAt = Date.now()) {
  const server = moment(serverTime);
  if (server.isValid()) {
    offsetMs = server.valueOf() - receivedAt;
  }
}

export function serverNow() {
  return Date.now() + offsetMs;
}

// For tests.
export function resetServerClock() {
  offsetMs = 0;
}
