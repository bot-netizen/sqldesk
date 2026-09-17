import { includes } from "lodash";
import React, { useEffect, useState } from "react";

import Alert from "antd/lib/alert";
import Link from "@/components/Link";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import EmptyState, { EmptyStateHelpMessage } from "@/components/empty-state/EmptyState";
import DynamicComponent from "@/components/DynamicComponent";
import BeaconConsent from "@/components/BeaconConsent";
import PlainButton from "@/components/PlainButton";

import { axios } from "@/services/axios";
import recordEvent from "@/services/recordEvent";
import { messages } from "@/services/auth";
import notification from "@/services/notification";
import routes from "@/services/routes";

import { DashboardAndQueryFavoritesList } from "./components/FavoritesList";
import HomeCounters from "./components/HomeCounters";
import ScheduledQueriesList from "./components/ScheduledQueriesList";
import { getHomeSummary } from "@/services/homeSummary";

import "./Home.less";

function DeprecatedEmbedFeatureAlert() {
  return (
    <Alert
      className="m-b-15"
      type="warning"
      message={
        <>
          You have enabled <code>ALLOW_PARAMETERS_IN_EMBEDS</code>. This setting is now deprecated and should be turned
          off. Parameters in embeds are supported by default.{" "}
          <Link
            href="https://tealdash.github.io/tealdash"
            target="_blank"
            rel="noopener noreferrer"
          >
            Read more
          </Link>
          .
        </>
      }
    />
  );
}

function EmailNotVerifiedAlert() {
  const verifyEmail = () => {
    axios.post("verification_email/").then((data) => {
      notification.success(data.message);
    });
  };

  return (
    <Alert
      className="m-b-15"
      type="warning"
      message={
        <>
          We have sent an email with a confirmation link to your email address. Please follow the link to verify your
          email address.{" "}
          <PlainButton type="link" onClick={verifyEmail}>
            Resend email
          </PlainButton>
          .
        </>
      }
    />
  );
}

export default function Home() {
  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(true);

  useEffect(() => {
    recordEvent("view", "page", "personal_homepage");
  }, []);

  useEffect(() => {
    let cancelled = false;
    getHomeSummary()
      .then((data) => {
        if (!cancelled) {
          setSummary(data);
        }
      })
      // The counters are not why anyone came here. If they cannot be had, the
      // favourites and the rest of the page still work.
      .catch(() => {})
      .finally(() => {
        if (!cancelled) {
          setLoadingSummary(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="home-page">
      <div className="container">
        {includes(messages, "using-deprecated-embed-feature") && <DeprecatedEmbedFeatureAlert />}
        {includes(messages, "email-not-verified") && <EmailNotVerifiedAlert />}
        {/* onboardingMode means this disappears of its own accord once every
            step it lists is done, leaving the page below. Inviting people is no
            longer one of those steps: it is not something you do before the
            tool is useful, and it kept the welcome panel on screen for anyone
            working alone. */}
        <DynamicComponent name="Home.EmptyState">
          <EmptyState
            header="Welcome to Tealdash 👋"
            description="Connect to any data source, easily visualize and share your data"
            illustration="dashboard"
            helpMessage={<EmptyStateHelpMessage helpTriggerType="GETTING_STARTED" />}
            showDashboardStep
            onboardingMode
          />
        </DynamicComponent>
        <DynamicComponent name="HomeExtra" />

        <HomeCounters counters={summary && summary.counters} loading={loadingSummary} />

        <div className="home-columns">
          <div className="home-column">
            <DashboardAndQueryFavoritesList />
          </div>
          <div className="home-column">
            <ScheduledQueriesList
              queries={summary ? summary.top_scheduled_queries : []}
              loading={loadingSummary}
            />
          </div>
        </div>

        <BeaconConsent />
      </div>
    </div>
  );
}

routes.register(
  "Home",
  routeWithUserSession({
    path: "/",
    title: "Tealdash",
    render: (pageProps) => <Home {...pageProps} />,
  })
);
