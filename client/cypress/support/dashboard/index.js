/* global cy */

import dashboardGridOptions from "../../../app/config/dashboard-grid-options";

/*
  The grid the dashboard actually uses, read from the application's own
  config rather than copied into each spec. Both numbers were copied, and
  both went stale when the grid went to twenty-four columns and rows half as
  tall -- the specs kept asserting a 50px row against a 25px one and read as
  seven product failures.

  `rowHeight` there is the row pitch. `DashboardGrid` hands react-grid-layout
  `rowHeight - margins` with a `margins` gutter, so a widget `rows` tall comes
  out `rowHeight * rows - margins`.
*/
export const GRID_ROW_HEIGHT = dashboardGridOptions.rowHeight;
export const GRID_MARGINS = dashboardGridOptions.margins;
export const gridRowsToPx = (rows) => GRID_ROW_HEIGHT * rows - GRID_MARGINS;

const { get } = Cypress._;
const RESIZE_HANDLE_SELECTOR = ".react-resizable-handle";

export function getWidgetTestId(widget) {
  return `WidgetId${widget.id}`;
}

export function createQueryAndAddWidget(dashboardId, queryData = {}, widgetOptions = {}) {
  return cy
    .createQuery(queryData)
    .then((query) => {
      const visualizationId = get(query, "visualizations.0.id");
      assert.isDefined(visualizationId, "Query api call returns at least one visualization with id");
      return cy.addWidget(dashboardId, visualizationId, widgetOptions);
    })
    .then(getWidgetTestId);
}

export function editDashboard() {
  cy.getByTestId("DashboardMoreButton").click();

  cy.getByTestId("DashboardMoreButtonMenu").contains("Edit").click();
}

export function shareDashboard() {
  cy.clickThrough(
    { button: "Publish" },
    `ShareDashboardButton
    OpenShareForm
    PublicAccessEnabled`
  );

  return cy.getByTestId("SecretAddress").invoke("val");
}

export function resizeBy(wrapper, offsetLeft = 0, offsetTop = 0) {
  return wrapper.within(() => {
    cy.get(RESIZE_HANDLE_SELECTOR).dragBy(offsetLeft, offsetTop, true);
  });
}
