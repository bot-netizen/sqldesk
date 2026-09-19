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
      // The server refreshes it now; nobody watching can add load.
      cy.getByTestId(elTestId).within(() => cy.getByTestId("RefreshButton").should("not.exist"));

      cy.getByTestId("LivePauseButton").click();
      cy.getByTestId("LiveBadge").should("contain", "Paused");

      cy.getByTestId("LivePauseButton").click();
      cy.getByTestId("LiveBadge").should("contain", "every 30 seconds");

      openLiveMenu();
      cy.getByTestId("LiveOff").click();
      cy.getByTestId("LiveBadge").should("not.exist");
      cy.getByTestId(elTestId).within(() => cy.getByTestId("RefreshButton").should("exist"));
    });
  });

  it("stays live across a reload, and the page checks in as a viewer", function () {
    cy.server();
    cy.route("POST", "**/live/watch").as("CheckIn");

    createQueryAndAddWidget(this.dashboardId, { query: "select 2 as n" }).then(() => {
      cy.visit(this.dashboardUrl);
      openLiveMenu();
      cy.getByTestId("LiveInterval.60").click();
      cy.getByTestId("LiveBadge").should("contain", "every minute");

      cy.reload();
      cy.getByTestId("LiveBadge").should("contain", "every minute");
      cy.wait("@CheckIn").then((xhr) => {
        expect(xhr.request.body.viewer).to.be.a("string").and.not.be.empty;
        expect(xhr.response.body.live.interval).to.equal(60);
      });
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
