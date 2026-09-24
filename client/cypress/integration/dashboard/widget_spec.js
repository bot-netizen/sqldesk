/* global cy */

import {
  createQueryAndAddWidget,
  editDashboard,
  resizeBy,
  GRID_ROW_HEIGHT,
  GRID_MARGINS,
} from "../../support/dashboard";

describe("Widget", () => {
  beforeEach(function () {
    cy.login();
    cy.createDashboard("Foo Bar").then(({ id }) => {
      this.dashboardId = id;
      this.dashboardUrl = `/dashboards/${id}`;
    });
  });

  const confirmDeletionInModal = () => {
    cy.get(".ant-modal .ant-btn").contains("Delete").click({ force: true });
  };

  it("adds widget", function () {
    cy.createQuery().then(({ id: queryId }) => {
      cy.visit(this.dashboardUrl);
      editDashboard();
      cy.getByTestId("AddWidgetButton").click();
      cy.getByTestId("AddWidgetDialog").within(() => {
        cy.get(`.query-selector-result[data-test="QueryId${queryId}"]`).click();
      });
      cy.contains("button", "Add to Dashboard").click();
      cy.getByTestId("AddWidgetDialog").should("not.exist");
      cy.get(".widget-wrapper").should("exist");
    });
  });

  it("removes widget", function () {
    createQueryAndAddWidget(this.dashboardId).then((elTestId) => {
      cy.visit(this.dashboardUrl);
      editDashboard();
      cy.getByTestId(elTestId).within(() => {
        cy.getByTestId("WidgetDeleteButton").click();
      });

      confirmDeletionInModal();
      cy.getByTestId(elTestId).should("not.exist");
    });
  });

  describe("Auto height for table visualization", () => {
    // The grid config these are derived from: a widget is a whole number of
    // rows tall. Asserting the relationship rather than a pixel count means a
    // deliberate change to how tall a table row is does not read as a failure,
    // while a widget that stops fitting its contents still does.
    const isWholeGridRows = (height) => (height + GRID_MARGINS) % GRID_ROW_HEIGHT === 0;

    // Nothing inside the widget may be cut off: auto height exists to make the
    // whole visualization visible without scrolling it.
    const assertContentFits = (elTestId) =>
      cy.getByTestId(elTestId).within(() => {
        cy.get(".visualization-renderer").should(($el) => {
          const el = $el[0];
          expect(el.scrollHeight, "visualization is not scrolled").to.be.at.most(el.clientHeight + 1);
        });
      });

    it("is a whole number of grid rows tall, and fits its contents", function () {
      const queryData = {
        query: "select s.a FROM generate_series(1,2) AS s(a)",
      };

      createQueryAndAddWidget(this.dashboardId, queryData).then((elTestId) => {
        cy.visit(this.dashboardUrl);
        cy.getByTestId(elTestId).its("0.offsetHeight").should("satisfy", isWholeGridRows);
        assertContentFits(elTestId);
      });
    });

    it("is taller for five rows than for two, and still fits them", function () {
      createQueryAndAddWidget(this.dashboardId, {
        query: "select s.a FROM generate_series(1,2) AS s(a)",
      }).then((smallTestId) => {
        cy.visit(this.dashboardUrl);
        cy.getByTestId(smallTestId)
          .its("0.offsetHeight")
          .then((smallHeight) => {
            createQueryAndAddWidget(this.dashboardId, {
              query: "select s.a FROM generate_series(1,5) AS s(a)",
            }).then((largeTestId) => {
              cy.visit(this.dashboardUrl);
              cy.getByTestId(largeTestId).its("0.offsetHeight").should("be.greaterThan", smallHeight);
              cy.getByTestId(largeTestId).its("0.offsetHeight").should("satisfy", isWholeGridRows);
              assertContentFits(largeTestId);
            });
          });
      });
    });

    describe("Height behavior on refresh", () => {
      const paramName = "count";
      const queryData = {
        query: `select s.a FROM generate_series(1,{{ ${paramName} }}) AS s(a)`,
        options: {
          parameters: [
            {
              title: paramName,
              name: paramName,
              type: "text",
            },
          ],
        },
      };

      beforeEach(function () {
        createQueryAndAddWidget(this.dashboardId, queryData).then((elTestId) => {
          cy.visit(this.dashboardUrl);
          cy.getByTestId(elTestId)
            .as("widget")
            .within(() => {
              cy.getByTestId("RefreshButton").as("refreshButton");
            });
          cy.getByTestId(`ParameterName-${paramName}`).within(() => {
            cy.getByTestId("TextParamInput").as("paramInput");
          });
        });
      });

      it("grows when dynamically adding table rows", () => {
        // listen to results
        cy.server();
        cy.route("GET", "**/api/query_results/*").as("FreshResults");

        // start with 1 table row
        cy.get("@paramInput").clear().type("1");
        cy.getByTestId("ParameterApplyButton").click();
        cy.wait("@FreshResults", { timeout: 10000 });

        cy.get("@widget")
          .invoke("height")
          .then((heightWithOneRow) => {
            // add 4 table rows
            cy.get("@paramInput").clear().type("5");
            cy.getByTestId("ParameterApplyButton").click();
            cy.wait("@FreshResults", { timeout: 10000 });

            cy.get("@widget").invoke("height").should("be.greaterThan", heightWithOneRow);
          });
      });

      it("revokes auto height after manual height adjustment", () => {
        // This is the behaviour that matters here: once somebody has sized a
        // widget by hand, new data must not move it again.
        cy.server();
        cy.route("GET", "**/api/query_results/*").as("FreshResults");

        editDashboard();

        // start with 1 table row
        cy.get("@paramInput").clear().type("1");
        cy.getByTestId("ParameterApplyButton").click();
        cy.wait("@FreshResults");

        // resize height by one grid row
        resizeBy(cy.get("@widget"), 0, GRID_ROW_HEIGHT);

        cy.get("@widget")
          .invoke("height")
          .then((resizedHeight) => {
            // add 4 table rows, which would have grown an auto-height widget
            cy.get("@paramInput").clear().type("5");
            cy.getByTestId("ParameterApplyButton").click();
            cy.wait("@FreshResults");

            cy.get("@widget").invoke("height").should("be.closeTo", resizedHeight, 2); // a drag can land a pixel off; a grid row is 50
          });
      });
    });
  });

  it("sets the correct height of table visualization", function () {
    const queryData = {
      query: `select '${"loremipsum".repeat(15)}' FROM generate_series(1,15)`,
    };

    const widgetOptions = { position: { col: 0, row: 0, sizeX: 3, sizeY: 10, autoHeight: false } };

    createQueryAndAddWidget(this.dashboardId, queryData, widgetOptions).then(() => {
      cy.visit(this.dashboardUrl);
      cy.getByTestId("TableVisualization").its("0.offsetHeight").should("be.oneOf", [380, 381]);
      cy.percySnapshot("Shows correct height of table visualization");
    });
  });

  it("shows fixed pagination for overflowing tabular content ", function () {
    const queryData = {
      query: "select 'lorem ipsum' FROM generate_series(1,50)",
    };

    const widgetOptions = { position: { col: 0, row: 0, sizeX: 3, sizeY: 10, autoHeight: false } };

    createQueryAndAddWidget(this.dashboardId, queryData, widgetOptions).then(() => {
      cy.visit(this.dashboardUrl);
      cy.getByTestId("TableVisualization").next(".ant-pagination.mini").should("be.visible");
      cy.percySnapshot("Shows fixed mini pagination for overflowing tabular content");
    });
  });

  it("keeps results on screen while refreshing", function () {
    const queryData = {
      query: "select pg_sleep({{sleep-time}}), 'sleep time: {{sleep-time}}' as sleeptime",
      options: { parameters: [{ name: "sleep-time", title: "Sleep time", type: "number", value: 0 }] },
    };

    createQueryAndAddWidget(this.dashboardId, queryData).then((elTestId) => {
      cy.visit(this.dashboardUrl);
      cy.getByTestId(elTestId).within(() => {
        cy.getByTestId("TableVisualization").should("contain", "sleep time: 0");
        cy.get(".refresh-indicator").should("not.be.visible");

        cy.getByTestId("ParameterName-sleep-time").type("10");
        cy.getByTestId("ParameterApplyButton").click();
        cy.get(".refresh-indicator").should("be.visible");
        cy.getByTestId("TableVisualization").should("contain", "sleep time: 0");
      });
    });
  });
});
