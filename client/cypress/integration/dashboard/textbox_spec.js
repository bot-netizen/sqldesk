/* global cy */

import { getWidgetTestId, editDashboard } from "../../support/dashboard";

describe("Textbox", () => {
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

  it("adds textbox", function () {
    cy.visit(this.dashboardUrl);
    editDashboard();
    cy.getByTestId("AddTextboxButton").click();
    cy.getByTestId("TextboxDialog").within(() => {
      cy.get("textarea").type("Hello World!");
    });
    cy.contains("button", "Add to Dashboard").click();
    cy.getByTestId("TextboxDialog").should("not.exist");
    cy.get(".widget-text").should("exist");
  });

  it("removes textbox by X button", function () {
    cy.addTextbox(this.dashboardId, "Hello World!")
      .then(getWidgetTestId)
      .then((elTestId) => {
        cy.visit(this.dashboardUrl);
        editDashboard();

        cy.getByTestId(elTestId).within(() => {
          cy.getByTestId("WidgetDeleteButton").click();
        });

        confirmDeletionInModal();
        cy.getByTestId(elTestId).should("not.exist");
      });
  });

  it("removes textbox by menu", function () {
    cy.addTextbox(this.dashboardId, "Hello World!")
      .then(getWidgetTestId)
      .then((elTestId) => {
        cy.visit(this.dashboardUrl);
        cy.getByTestId(elTestId).within(() => {
          cy.getByTestId("WidgetDropdownButton").click();
        });
        cy.getByTestId("WidgetDropdownButtonMenu").contains("Remove from Dashboard").click();

        confirmDeletionInModal();
        cy.getByTestId(elTestId).should("not.exist");
      });
  });

  it("allows opening menu after removal", function () {
    let elTestId1;
    cy.addTextbox(this.dashboardId, "txb 1")
      .then(getWidgetTestId)
      .then((elTestId) => {
        elTestId1 = elTestId;
        return cy.addTextbox(this.dashboardId, "txb 2").then(getWidgetTestId);
      })
      .then((elTestId2) => {
        cy.visit(this.dashboardUrl);
        editDashboard();

        // remove 1st textbox and make sure it's gone
        cy.getByTestId(elTestId1)
          .as("textbox1")
          .within(() => {
            cy.getByTestId("WidgetDeleteButton").click();
          });

        confirmDeletionInModal();
        cy.get("@textbox1").should("not.exist");

        // remove 2nd textbox and make sure it's gone
        cy.getByTestId(elTestId2)
          .as("textbox2")
          .within(() => {
            // unclickable while the textbox is in edit mode
            cy.getByTestId("WidgetDeleteButton").click();
          });

        confirmDeletionInModal();
        cy.get("@textbox2").should("not.exist"); // <-- fails because of the bug
      });
  });

  it("edits textbox", function () {
    cy.addTextbox(this.dashboardId, "Hello World!")
      .then(getWidgetTestId)
      .then((elTestId) => {
        cy.visit(this.dashboardUrl);
        cy.getByTestId(elTestId)
          .as("textboxEl")
          .within(() => {
            cy.getByTestId("WidgetDropdownButton").click();
          });

        cy.getByTestId("WidgetDropdownButtonMenu").contains("Edit").click();

        const newContent = "[edited]";
        cy.getByTestId("TextboxDialog")
          .should("exist")
          .within(() => {
            cy.get("textarea").clear().type(newContent);
            cy.contains("button", "Save").click();
          });

        cy.get("@textboxEl").should("contain", newContent);
      });
  });

  it("renders textbox according to position configuration", function () {
    const id = this.dashboardId;
    const txb1Pos = { col: 0, row: 0, sizeX: 3, sizeY: 2 };
    const txb2Pos = { col: 1, row: 1, sizeX: 3, sizeY: 4 };
    const GRID_ROW_HEIGHT = 50;

    cy.viewport(1215, 800);
    cy.addTextbox(id, "x", { position: txb1Pos })
      .then(getWidgetTestId)
      .then((firstTestId) => {
        cy.addTextbox(id, "x", { position: txb2Pos })
          .then(getWidgetTestId)
          .then((secondTestId) => {
            cy.visit(this.dashboardUrl);

            // Positions are compared between the two widgets rather than
            // against the viewport: how far the grid sits from the top of the
            // page is page chrome, and moving the navigation to a top bar
            // changed it without changing any widget's place on the grid.
            cy.getByTestId(firstTestId).then(($first) => {
              const first = $first.offset();
              // Both textboxes span `sizeX` columns, so one column is that
              // width plus its margin divided by how many columns it covers.
              const columnWidth = ($first.width() + 15) / txb1Pos.sizeX;

              cy.getByTestId(secondTestId).should(($second) => {
                const second = $second.offset();

                expect(second.left - first.left, "one column to the right").to.be.closeTo(columnWidth, 1);

                // The second textbox asks for row 1, but the first is two rows
                // tall and they share columns -- so the grid puts it on the
                // next free row instead of letting them overlap. It lands
                // directly beneath, a margin clear of the one above.
                expect(second.top - first.top, "clear of the widget above").to.be.closeTo($first.height() + 15, 1);
                expect($second.width(), "same width, both are three columns").to.eq($first.width());
                expect($second.height(), "four grid rows tall").to.eq(4 * GRID_ROW_HEIGHT - 15);
              });
            });
          });
      });
  });
});
