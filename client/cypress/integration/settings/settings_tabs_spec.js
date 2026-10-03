describe("Settings Tabs", () => {
  const regularUser = {
    name: "Example User",
    email: "user@sqldesk.io",
    password: "password",
  };

  const userTabs = ["Users", "Groups", "Query Snippets", "Account"];
  const adminTabs = ["Data Sources", "Alert Destinations", "General"];

  const expectSettingsTabsToBe = (expectedTabs) =>
    cy.getByTestId("SettingsScreenItem").then(($list) => {
      const listedPages = $list.toArray().map((el) => el.text);
      expect(listedPages).to.have.members(expectedTabs);
    });

  /*
    Settings is a named menu in the top row, not a gear on the right.

    It moved there because what it holds depends entirely on who you are: an
    administrator sees data sources, groups and the organisation's settings,
    and everybody else sees their own account and their snippets. An icon
    cannot say that. These specs used to click `SettingsLink`, the gear, which
    went straight to the first page the person was allowed to open.
  */
  const openSettingsMenu = () => cy.getByTestId("SettingsMenuButton").click();
  const settingsMenuItems = () => cy.get(".desktop-navbar-dropdown-menu a");

  before(() => {
    cy.login().then(() => cy.createUser(regularUser));
  });

  describe("For admin user", () => {
    beforeEach(() => {
      cy.logout();
      cy.login();
      cy.visit("/");
    });

    it("the menu opens on the pages an administrator may see", () => {
      openSettingsMenu();
      settingsMenuItems().should("contain.text", "Data Sources");
    });

    it("and goes to the one it is clicked on", () => {
      openSettingsMenu();
      settingsMenuItems().contains("Data Sources").click();
      cy.url().should("include", "/data_sources");
    });

    it("all tabs should be available", () => {
      cy.visit("/data_sources");
      expectSettingsTabsToBe([...userTabs, ...adminTabs]);
    });
  });

  describe("For regular user", () => {
    beforeEach(() => {
      cy.logout();
      cy.login(regularUser.email, regularUser.password);
      cy.visit("/");
    });

    it("the menu offers only what they may open", () => {
      openSettingsMenu();
      settingsMenuItems().should("contain.text", "Account");
      settingsMenuItems().should("not.contain.text", "Data Sources");
    });

    it("limited set of settings tabs should be available", () => {
      cy.visit("/users/me");
      expectSettingsTabsToBe(userTabs);
    });
  });
});
