import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";

/*
  How wide this screen draws a dashboard, told to the server so the pictures
  sent in this person's name are drawn the same way.

  A dashboard's widgets keep their height and take their width from the
  screen, so tiles and table columns that fit on a wide monitor wrap out of
  sight on a narrow one. Export as image photographs the dashboard on this
  screen; the server's renderer used a window of its own, so the Slack
  picture of the same dashboard showed eight tiles where the export showed
  eighteen. Reported whenever somebody exports, sends or subscribes -- the
  moments they decide what the picture should look like -- and used by
  Send to Slack, subscriptions and alerts alike (sqldesk/screenshots.py).

  Never the reason any of those fail: an install too old to have the
  endpoint, or a request that does not arrive, only means the picture keeps
  the renderer's own width.
*/

export const MIN_WIDTH = 600;
export const MAX_WIDTH = 3840;

/** The dashboard's width on this screen, in CSS pixels, or null. */
export function dashboardWidth(doc = document) {
  const element = doc.getElementById("dashboard-container");
  if (!element) {
    return null;
  }
  const width = Math.round(element.getBoundingClientRect().width);
  return width >= MIN_WIDTH && width <= MAX_WIDTH ? width : null;
}

/** This browser's time zone, such as "America/Toronto", or null. */
export function timeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch (error) {
    return null;
  }
}

/**
 * The order each table on the page is showing, by widget id -- only the ones
 * somebody has sorted. Clicking a header sorts in the browser alone, so a
 * picture drawn by the server showed the query's order where the export
 * showed this one.
 */
export function tableOrders(doc = document) {
  const orders = {};
  doc.querySelectorAll("[data-widgetid]").forEach((widget) => {
    const table = widget.querySelector("[data-table-order]");
    if (!table) {
      return;
    }
    try {
      const order = JSON.parse(table.getAttribute("data-table-order"));
      if (Array.isArray(order) && order.length > 0) {
        orders[widget.getAttribute("data-widgetid")] = order;
      }
    } catch (error) {
      // Not an order this page wrote; leave that table in the query's order.
    }
  });
  return orders;
}

/**
 * Tell the server how this screen draws a dashboard: its width, the time
 * zone, and the order its tables are in. Resolves either way, so a caller can
 * wait for it before sending without being able to fail on it.
 */
export function rememberScreen({ dashboardId = null, doc = document } = {}) {
  if (!currentUser || !currentUser.id || !doc.getElementById("dashboard-container")) {
    return Promise.resolve(null);
  }
  const body = {};
  const width = dashboardWidth(doc);
  if (width) {
    body.width = width;
    const zone = timeZone();
    if (zone) {
      body.time_zone = zone;
    }
  }
  if (dashboardId) {
    body.dashboard_id = dashboardId;
    body.table_orders = tableOrders(doc);
  }
  if (!body.width && !body.dashboard_id) {
    return Promise.resolve(null);
  }
  return axios.post(`api/users/${currentUser.id}/screen`, body).catch(() => null);
}
