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
    // The seeded admin has no picture, so the navbar draws initials rather
    // than an <img>. Avatars are worked out locally now instead of being
    // fetched from gravatar, which is the whole point of the change -- this
    // asserted the gravatar era and would pass again only if it came back.
    //
    // Two letters rather than the exact pair: edit_profile_spec runs before
    // this one and renames the admin, restoring the name at the end of its
    // own test. Pinning the letters here would make this fail for that
    // spec's reasons. Which letters come from which field is pinned in
    // UserAvatar.test.js, where nothing else can disturb it.
    cy.getByTestId("ProfileDropdown")
      .find(".user-avatar-initials")
      .invoke("text")
      .should("match", /^[A-Z]{2}$/);

    cy.wait(1000); // eslint-disable-line cypress/no-unnecessary-waiting
    cy.percySnapshot("Homepage");
  });
});
