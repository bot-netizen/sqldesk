/**
 * Counts pixels drawn in a series colour.
 *
 * ECharts renders to a canvas, so there is no `g.points` element to look for --
 * and a canvas is present whether or not anything was plotted, which makes
 * "does the element exist" useless as a test. Axes and gridlines are grey, and
 * every series colour is saturated, so saturation separates "a chart with data"
 * from "an empty pair of axes".
 */
function countSeriesPixels($canvases) {
  let count = 0;
  // ECharts draws on more than one canvas when it needs layers, and which layer
  // holds the series is not fixed -- so count across all of them rather than
  // assuming the first one is the interesting one.
  $canvases.each((_, canvas) => {
    const { data } = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);
    for (let i = 0; i < data.length; i += 4) {
      const [r, g, b, a] = [data[i], data[i + 1], data[i + 2], data[i + 3]];
      if (a > 10 && Math.max(r, g, b) - Math.min(r, g, b) > 30) {
        count += 1;
      }
    }
  });
  return count;
}

/**
 * Asserts whether the visualization preview has actually plotted something.
 * @param should "exist" to require plotted data, "not.exist" to require none
 */
export function assertPlotPreview(should = "exist") {
  cy.getByTestId("VisualizationPreview")
    .find("canvas")
    .should("exist")
    .then(($canvases) => {
      const drawn = countSeriesPixels($canvases);
      if (should === "not.exist") {
        expect(drawn, "pixels drawn in a series colour").to.equal(0);
      } else {
        expect(drawn, "pixels drawn in a series colour").to.be.greaterThan(0);
      }
    });
}

/** The same check, for a chart rendered inside a dashboard widget. */
export function assertWidgetPlotted() {
  cy.get("canvas")
    .should("exist")
    .then(($canvases) => {
      expect(countSeriesPixels($canvases), "pixels drawn in a series colour").to.be.greaterThan(0);
    });
}

export function createChartThroughUI(chartName, chartSpecificAssertionFn = () => {}) {
  cy.getByTestId("NewVisualization").click();
  cy.getByTestId("VisualizationType").selectAntdOption("VisualizationType.CHART");
  cy.getByTestId("VisualizationName").clear().type(chartName);

  chartSpecificAssertionFn();

  cy.server();
  cy.route("POST", "**/api/visualizations").as("SaveVisualization");

  cy.getByTestId("EditVisualizationDialog").contains("button", "Save").click();

  cy.getByTestId("QueryPageVisualizationTabs").contains("span", chartName).should("exist");

  cy.wait("@SaveVisualization").should("have.property", "status", 200);

  return cy.get("@SaveVisualization").then((xhr) => {
    const { id, name, options } = xhr.response.body;
    return cy.wrap({ id, name, options });
  });
}

export function assertTabbedEditor(chartSpecificTabbedEditorAssertionFn = () => {}) {
  cy.getByTestId("Chart.GlobalSeriesType").should("exist");

  cy.getByTestId("VisualizationEditor.Tabs.Series").click();
  cy.getByTestId("VisualizationEditor").find("table").should("exist");

  cy.getByTestId("VisualizationEditor.Tabs.Colors").click();
  cy.getByTestId("VisualizationEditor").find("table").should("exist");

  cy.getByTestId("VisualizationEditor.Tabs.DataLabels").click();
  cy.getByTestId("VisualizationEditor").getByTestId("Chart.DataLabels.ShowDataLabels").should("exist");

  chartSpecificTabbedEditorAssertionFn();

  cy.getByTestId("VisualizationEditor.Tabs.General").click();
}

export function assertAxesAndAddLabels(xaxisLabel, yaxisLabel) {
  cy.getByTestId("VisualizationEditor.Tabs.XAxis").click();
  cy.getByTestId("Chart.XAxis.Type").contains(".ant-select-selection-item", "Auto Detect").should("exist");

  cy.getByTestId("Chart.XAxis.Name").clear().type(xaxisLabel);

  cy.getByTestId("VisualizationEditor.Tabs.YAxis").click();
  cy.getByTestId("Chart.LeftYAxis.Type").contains(".ant-select-selection-item", "Linear").should("exist");

  cy.getByTestId("Chart.LeftYAxis.Name").clear().type(yaxisLabel);

  cy.getByTestId("Chart.LeftYAxis.TickFormat").clear().type("+");

  cy.getByTestId("VisualizationEditor.Tabs.General").click();
}

export function createDashboardWithCharts(title, chartGetters, widgetsAssertionFn = () => {}) {
  cy.createDashboard(title).then((dashboard) => {
    const dashboardUrl = `/dashboards/${dashboard.id}`;
    const widgetGetters = chartGetters.map((chartGetter) => `${chartGetter}Widget`);

    chartGetters.forEach((chartGetter, i) => {
      const position = { autoHeight: false, sizeY: 8, sizeX: 3, col: (i % 2) * 3 };
      cy.get(`@${chartGetter}`)
        .then((chart) => cy.addWidget(dashboard.id, chart.id, { position }))
        .as(widgetGetters[i]);
    });

    widgetsAssertionFn(widgetGetters, dashboardUrl);
  });
}
