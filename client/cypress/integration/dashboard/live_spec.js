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

  it("says so when Refresh has nothing newer to show", function () {
    // A query nobody has run: the page's first load runs it, so its result is
    // seconds old when Refresh is pressed, and Refresh reuses it.
    createQueryAndAddWidget(this.dashboardId, { query: `select ${Date.now()} as n` }).then((elTestId) => {
      cy.visit(this.dashboardUrl);
      cy.getByTestId(elTestId).within(() => cy.getByTestId("RefreshButton").click());
      cy.contains(".ant-notification-notice", "Already up to date").should("exist");
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
