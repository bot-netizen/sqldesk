import React, { useState } from "react";
import Card from "antd/lib/card";
import Button from "antd/lib/button";
import Typography from "antd/lib/typography";
import { clientConfig } from "@/services/auth";
import Link from "@/components/Link";
import DynamicComponent from "@/components/DynamicComponent";
import OrgSettings from "@/services/organizationSettings";

const Text = Typography.Text;

function BeaconConsent() {
  const [hide, setHide] = useState(false);

  // Only shown when this installation has a version-check endpoint configured.
  // With no endpoint the setting governs nothing, and asking would be noise.
  if (!clientConfig.showBeaconConsentMessage || hide) {
    return null;
  }

  const hideConsentCard = () => {
    clientConfig.showBeaconConsentMessage = false;
    setHide(true);
  };

  const confirmConsent = (confirm) => {
    OrgSettings.save({ beacon_consent: confirm }, "Settings saved.").finally(hideConsentCard);
  };

  return (
    <DynamicComponent name="BeaconConsent">
      <div className="m-t-10 tiled">
        <Card title="Include usage counts when checking for new versions?" bordered={false}>
          <Text>
            This installation checks for new versions at an address its administrator configured. These counts can be
            sent along with that check:
          </Text>
          <div className="m-t-5">
            <ul>
              <li>Number of users, queries, dashboards, alerts, widgets and visualizations.</li>
              <li>Types of data sources, alert destinations and visualizations.</li>
            </ul>
          </div>
          <Text>
            Counts only — no query text, names, results or credentials. Nothing is sent to the Tealdash project, which
            runs no servers and collects nothing.
          </Text>
          <div className="m-t-5">
            <Button type="primary" className="m-r-5" onClick={() => confirmConsent(true)}>
              Include them
            </Button>
            <Button type="default" onClick={() => confirmConsent(false)}>
              Version only
            </Button>
          </div>
          <div className="m-t-15">
            <Text type="secondary">
              You can change this anytime on the <Link href="settings/general">Settings</Link> page.
            </Text>
          </div>
        </Card>
      </div>
    </DynamicComponent>
  );
}

export default BeaconConsent;
