describe("Login", () => {
  beforeEach(() => {
    cy.visit("/login");
  });

  it("greets the user and take a screenshot", () => {
    cy.contains("h3", "Login to SQLDesk");

    cy.wait(1000); // eslint-disable-line cypress/no-unnecessary-waiting
    cy.percySnapshot("Login");
  });

  it("shows message on failed login", () => {
    cy.getByTestId("Email").type("admin@sqldesk.io");
    cy.getByTestId("Password").type("wrongpassword{enter}");

    cy.getByTestId("ErrorMessage").should("contain", "Wrong email or password.");
  });

  it("navigates to homepage with successful login", () => {
    cy.getByTestId("Email").type("admin@sqldesk.io");
    cy.getByTestId("Password").type("password{enter}");

    cy.title().should("eq", "SQLDesk");
    cy.getByTestId("ProfileDropdown").find("img.profile__image_thumb").should("exist");

    cy.wait(1000); // eslint-disable-line cypress/no-unnecessary-waiting
    cy.percySnapshot("Homepage");
  });
});
