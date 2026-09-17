import React from "react";
import Form from "antd/lib/form";
import Checkbox from "antd/lib/checkbox";
import Skeleton from "antd/lib/skeleton";
import Typography from "antd/lib/typography";
import DynamicComponent from "@/components/DynamicComponent";
import { SettingsEditorPropTypes, SettingsEditorDefaultProps } from "../prop-types";

export default function BeaconConsentSettings(props) {
  const { values, onChange, loading } = props;

  return (
    <DynamicComponent name="OrganizationSettings.BeaconConsentSettings" {...props}>
      <Form.Item label="Usage Counts in Version Check">
        {loading ? (
          <Skeleton title={{ width: 300 }} paragraph={false} active />
        ) : (
          <React.Fragment>
            <Checkbox
              name="beacon_consent"
              checked={values.beacon_consent}
              onChange={(e) => onChange({ beacon_consent: e.target.checked })}
            >
              Include aggregate counts when checking for new versions
            </Checkbox>
            <div className="m-t-5">
              <Typography.Text type="secondary">
                Counts of users, queries, dashboards, alerts, widgets, visualizations and data source types — no query
                text, names, results or credentials. They go only to the endpoint set in{" "}
                <code>SQLDESK_VERSION_CHECK_URL</code>, and nothing is sent when that is unset.
              </Typography.Text>
            </div>
          </React.Fragment>
        )}
      </Form.Item>
    </DynamicComponent>
  );
}

BeaconConsentSettings.propTypes = SettingsEditorPropTypes;

BeaconConsentSettings.defaultProps = SettingsEditorDefaultProps;
