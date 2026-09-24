/* global cy */

import { getWidgetTestId, editDashboard, resizeBy, gridRowsToPx } from "../../support/dashboard";

// Navigation is a top bar, so nothing is reserved to the left of the content.
const menuWidth = 0;

describe("Grid compliant widgets", () => {
  beforeEach(function () {
    cy.login();
    cy.viewport(1215 + menuWidth, 800);
    cy.createDashboard("Foo Bar")
      .then(({ id }) => {
        this.dashboardUrl = `/dashboards/${id}`;
        // Six by six, which is what three by three was before the grid
        // doubled -- the pixel counts below are the same widget, not a
        // smaller one. The fixture's own default is still 3x3, which is
        // under the minimum now and silently clamps.
        return cy
          .addTextbox(id, "Hello World!", { position: { col: 0, row: 0, sizeX: 6, sizeY: 6 } })
          .then(getWidgetTestId);
      })
      .then((elTestId) => {
        cy.visit(this.dashboardUrl);
        cy.getByTestId(elTestId).as("textboxEl");
      });
  });

  describe("Draggable", () => {
    describe("Grid snap", () => {
      beforeEach(() => {
        editDashboard();
      });

      it("stays put when dragged under snap threshold", () => {
        cy.get("@textboxEl")
          .dragBy(30)
          .invoke("offset")
          .should("have.property", "left", 15 + menuWidth); // no change, 15 -> 15
      });

      it("moves one column when dragged over snap threshold", () => {
        cy.get("@textboxEl")
          .dragBy(110)
          .invoke("offset")
          .should("have.property", "left", 115 + menuWidth); //  moved by 100, 15 -> 115
      });

      it("moves two columns when dragged over snap threshold", () => {
        cy.get("@textboxEl")
          .dragBy(200)
          .invoke("offset")
          .should("have.property", "left", 215 + menuWidth); //  moved by 200, 15 -> 215
      });
    });

    it("saves a drag when editing is done, and not before", () => {
      cy.server();
      cy.route("POST", "**/api/widgets/*").as("WidgetSave");

      editDashboard();
      cy.get("@textboxEl").dragBy(100);

      // The move is in the browser only until Done Editing is pressed --
      // dragging used to write to the server about two seconds later, so a
      // dashboard was changed by anyone who opened it and nudged something.
      cy.contains(".save-status", "Unsaved changes").should("exist");
      cy.get("@WidgetSave.all").should("have.length", 0);

      cy.contains("button", "Done Editing").click();
      cy.wait("@WidgetSave");
    });
  });

  describe("Resizeable", () => {
    describe("Column snap", () => {
      beforeEach(() => {
        editDashboard();
      });

      it("stays put when dragged under snap threshold", () => {
        resizeBy(cy.get("@textboxEl"), 30)
          .then(() => cy.get("@textboxEl"))
          .invoke("width")
          .should("eq", 285); // no change, 285 -> 285
      });

      it("moves one column when dragged over snap threshold", () => {
        resizeBy(cy.get("@textboxEl"), 110)
          .then(() => cy.get("@textboxEl"))
          .invoke("width")
          .should("eq", 385); // resized by 200, 185 -> 385
      });

      it("moves two columns when dragged over snap threshold", () => {
        resizeBy(cy.get("@textboxEl"), 400)
          .then(() => cy.get("@textboxEl"))
          .invoke("width")
          .should("eq", 685); // resized by 400, 285 -> 685
      });
    });

    describe("Row snap", () => {
      beforeEach(() => {
        editDashboard();
      });

      it("stays put when dragged under snap threshold", () => {
        resizeBy(cy.get("@textboxEl"), 0, 10)
          .then(() => cy.get("@textboxEl"))
          .invoke("height")
          .should("eq", gridRowsToPx(6)); // no change, six rows either way
      });

      it("moves one row when dragged over snap threshold", () => {
        resizeBy(cy.get("@textboxEl"), 0, 30)
          .then(() => cy.get("@textboxEl"))
          .invoke("height")
          .should("eq", gridRowsToPx(7)); // one row taller, and a row is 25px now
      });

      it("shrinks to minimum", () => {
        cy.get("@textboxEl")
          .then(($el) => resizeBy(cy.get("@textboxEl"), -$el.width(), -$el.height())) // resize to 0,0
          .then(() => cy.get("@textboxEl"))
          .should(($el) => {
            expect($el.width()).to.eq(185); // min textbox width
            expect($el.height()).to.eq(gridRowsToPx(4)); // min textbox height
          });
      });
    });

    it("saves a resize when editing is done, and not before", () => {
      cy.server();
      cy.route("POST", "**/api/widgets/*").as("WidgetSave");

      editDashboard();
      resizeBy(cy.get("@textboxEl"), 200);

      cy.contains(".save-status", "Unsaved changes").should("exist");
      cy.get("@WidgetSave.all").should("have.length", 0);

      cy.contains("button", "Done Editing").click();
      cy.wait("@WidgetSave");
    });

    it("puts a discarded resize back where it was", () => {
      cy.server();
      cy.route("POST", "**/api/widgets/*").as("WidgetSave");

      editDashboard();
      cy.get("@textboxEl")
        .invoke("width")
        .then((widthBefore) => {
          resizeBy(cy.get("@textboxEl"), 200);
          cy.get("@textboxEl").invoke("width").should("not.eq", widthBefore);

          cy.getByTestId("DashboardDiscardButton").click();
          cy.get(".ant-modal-confirm").contains("button", "Discard").click();

          cy.get("@textboxEl").invoke("width").should("eq", widthBefore);
          cy.get("@WidgetSave.all").should("have.length", 0);
        });
    });
  });
});
