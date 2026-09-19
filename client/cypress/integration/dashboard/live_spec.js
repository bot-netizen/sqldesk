/* global cy */

import { createQueryAndAddWidget } from "../../support/dashboard";

function openLiveMenu() {
  cy.getByTestId("DashboardMoreButton").click();
  cy.getByTestId("LiveMenu").click();
}

describe("Live dashboards", () => {
  beforeEach(function () {
    cy.login();
    cy.createDashboard("Live board").then(({ id }) => {
      this.dashboardId = id;
      this.dashboardUrl = `/dashboards/${id}`;
    });
  });

  it("goes live, pauses, resumes and turns off", function () {
    createQueryAndAddWidget(this.dashboardId, { query: "select 1 as n" }).then((elTestId) => {
      cy.visit(this.dashboardUrl);
      // An ordinary dashboard: a Refresh button, and one on each widget.
      cy.getByTestId(elTestId).within(() => cy.getByTestId("RefreshButton").should("exist"));
      cy.getByTestId("LiveBadge").should("not.exist");

      openLiveMenu();
      cy.getByTestId("LiveInterval.30").click();

      cy.getByTestId("LiveBadge").should("contain", "Live").and("contain", "every 30 seconds");
      // The server refreshes it now; nobody watching can add load. What the
      // widget shows instead is when the next refresh comes -- only that.
      cy.getByTestId(elTestId).within(() => {
        cy.getByTestId("RefreshButton").should("not.exist");
        cy.getByTestId("LiveCountdown")
          .invoke("text")
          .should("match", /^(next in \d+s|refreshing…)$/);
      });

      cy.getByTestId("LivePauseButton").click();
      cy.getByTestId("LiveBadge").should("contain", "Paused");
      // Paused, nothing is coming: it says how old the result is instead.
      cy.getByTestId(elTestId).within(() => cy.getByTestId("LiveCountdown").should("contain", "updated"));

      cy.getByTestId("LivePauseButton").click();
      cy.getByTestId("LiveBadge").should("contain", "every 30 seconds");

      openLiveMenu();
      cy.getByTestId("LiveOff").click();
      cy.getByTestId("LiveBadge").should("not.exist");
      cy.getByTestId(elTestId).within(() => cy.getByTestId("RefreshButton").should("exist"));
    });
  });

  it("draws each result the server makes, and counts down again, without a reload", function () {
    // A value that is different every time the query runs.
    createQueryAndAddWidget(this.dashboardId, { query: "select clock_timestamp()::text as t" }).then((elTestId) => {
      cy.visit(this.dashboardUrl);
      // Load it once so the query has a result, then again: a dashboard whose
      // queries already have results is the case that matters. The page then
      // knows each query's latest result, and a live reload that reused that
      // instead of fetching the server's new one drew nothing new, ever.
      cy.getByTestId(elTestId).find(".ant-table-tbody td").should("exist");
      cy.reload();
      cy.getByTestId(elTestId)
        .find(".ant-table-tbody td")
        .first()
        .invoke("text")
        .then((before) => {
          openLiveMenu();
          cy.getByTestId("LiveInterval.30").click();
          cy.getByTestId("LiveBadge").should("contain", "every 30 seconds");

          // The server refreshes it about 30 seconds after the first result;
          // the new one has to reach the screen by itself.
          cy.getByTestId(elTestId)
            .find(".ant-table-tbody td", { timeout: 90000 })
            .should(($cells) => {
              expect($cells.first().text()).not.to.equal(before);
            });
          cy.getByTestId(elTestId).within(() => cy.getByTestId("LiveCountdown").should("contain", "next in"));
        });
    });
  });

  it("stays live across a reload, and the page checks in as a viewer", function () {
    createQueryAndAddWidget(this.dashboardId, { query: "select 2 as n" }).then(() => {
      cy.visit(this.dashboardUrl);
      openLiveMenu();
      cy.getByTestId("LiveInterval.60").click();
      cy.getByTestId("LiveBadge").should("contain", "every minute");

      cy.reload();
      cy.getByTestId("LiveBadge").should("contain", "every minute");
      // Listen only from here: a check-in the reload cut off has no reply. The
      // reloaded page checks in again within 15 seconds.
      cy.intercept("POST", "**/live/watch").as("CheckIn");
      cy.wait("@CheckIn", { timeout: 30000 }).then(({ request, response }) => {
        expect(request.body.viewer).to.be.a("string").and.not.be.empty;
        expect(request.body.leaving).to.be.undefined;
        expect(response.body.live.interval).to.equal(60);
        expect(response.body.server_time).to.be.a("string");
      });
    });
  });

  it("Refresh runs the queries again, however recent their results", function () {
    createQueryAndAddWidget(this.dashboardId, { query: "select 4 as n" }).then((elTestId) => {
      cy.visit(this.dashboardUrl);
      cy.getByTestId(elTestId).find(".ant-table-tbody td").should("exist");
      // Again, now that the query has a result the page knows about: Refresh
      // used to fetch that same result instead of running the query.
      cy.reload();
      cy.getByTestId(elTestId).find(".ant-table-tbody td").should("exist");

      cy.intercept("POST", "**/api/queries/*/results").as("Run");
      cy.getByTestId(elTestId).within(() => cy.getByTestId("RefreshButton").click());
      cy.wait("@Run").its("request.body.max_age").should("equal", 0);
    });
  });

  it("offers no auto-refresh faster than ten minutes on an ordinary dashboard", function () {
    createQueryAndAddWidget(this.dashboardId, { query: "select 3 as n" }).then(() => {
      cy.visit(this.dashboardUrl);
      cy.getByTestId("DashboardRefreshRateButton").click();
      cy.getByTestId("DashboardRefreshRateMenu").within(() => {
        cy.contains("10 minutes").should("exist");
        cy.contains(/^1 minute$/).should("not.exist");
        cy.contains(/^5 minutes$/).should("not.exist");
      });
    });
  });
});
