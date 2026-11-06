import debug from "debug";
import { includes, extend } from "lodash";
import location from "@/services/location";
import { axios } from "@/services/axios";
import { notifySessionRestored } from "@/services/restoreSession";

export const currentUser = {
  _isAdmin: undefined,

  canEdit(object) {
    const userId = object.user_id || (object.user && object.user.id);
    return this.isAdmin || (userId && userId === this.id);
  },

  canCreate() {
    return (
      this.hasPermission("create_query") || this.hasPermission("create_dashboard") || this.hasPermission("list_alerts")
    );
  },

  hasPermission(permission) {
    if (permission === "admin" && this._isAdmin !== undefined) {
      return this._isAdmin;
    }
    return includes(this.permissions, permission);
  },

  /*
    Whether this person may use a feature an admin hands to a group, by the
    same rule the server applies in sqldesk/features.py: the install has to
    offer it at all, and then an admin has it or a group was granted it.

    Asked here so a page can hide what the server would refuse; the server
    is still what decides.
    */
  can(feature) {
    const offered = (clientConfig.grantableFeatures || []).some((entry) => entry.name === feature);
    return offered && (this.isAdmin || this.hasPermission(feature));
  },

  get isAdmin() {
    return this.hasPermission("admin");
  },

  set isAdmin(isAdmin) {
    this._isAdmin = isAdmin;
  },
};

export const clientConfig = {};
export const messages = [];

/*
  Whether a feature is still settling, as `sqldesk/features.py` says.

  Asked rather than listed here: a page that carried its own idea of which
  features are beta is a page that keeps badging one after it has left beta,
  and the badge is only worth drawing while it is true.
*/
export function featureIsBeta(name) {
  const entry = (clientConfig.grantableFeatures || []).find((one) => one.name === name);
  return !!(entry && entry.beta);
}

const logger = debug("sqldesk:auth");
const session = { loaded: false };

const AuthUrls = {
  Login: "login",
};

export function updateClientConfig(newClientConfig) {
  extend(clientConfig, newClientConfig);
}

function updateSession(sessionData) {
  logger("Updating session to be:", sessionData);
  extend(session, sessionData, { loaded: true });
  extend(currentUser, session.user);
  extend(clientConfig, session.client_config);
  extend(messages, session.messages);
}

export const Auth = {
  isAuthenticated() {
    return session.loaded && session.user.id;
  },
  getLoginUrl() {
    return AuthUrls.Login;
  },
  setLoginUrl(loginUrl) {
    AuthUrls.Login = loginUrl;
  },
  login() {
    const next = encodeURI(location.url);
    logger("Calling login with next = %s", next);
    window.location.href = `${AuthUrls.Login}?next=${next}`;
  },
  logout() {
    logger("Logout.");
    window.location.href = "logout";
  },
  loadSession() {
    logger("Loading session");
    if (session.loaded && session.user.id) {
      logger("Resolving with local value.");
      return Promise.resolve(session);
    }

    Auth.setApiKey(null);
    return axios.get("api/session").then((data) => {
      updateSession(data);
      return session;
    });
  },
  loadConfig() {
    logger("Loading config");
    return axios.get("/api/config").then((data) => {
      updateSession({ client_config: data.client_config, user: { permissions: [] }, messages: [] });
      return data;
    });
  },
  setApiKey(apiKey) {
    logger("Set API key to: %s", apiKey);
    Auth.apiKey = apiKey;
  },
  getApiKey() {
    return Auth.apiKey;
  },
  requireSession() {
    logger("Requested authentication");
    if (Auth.isAuthenticated()) {
      return Promise.resolve(session);
    }
    return Auth.loadSession()
      .then(() => {
        if (Auth.isAuthenticated()) {
          logger("Loaded session");
          notifySessionRestored();
          return session;
        }
        logger("Need to login, redirecting");
        Auth.login();
      })
      .catch(() => {
        logger("Need to login, redirecting");
        Auth.login();
      });
  },
};
