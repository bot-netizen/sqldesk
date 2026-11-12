import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import { find, get } from "lodash";
import Alert from "antd/lib/alert";
import Select from "antd/lib/select";

import { axios } from "@/services/axios";

/*
  A Slack channel, picked from the ones the app has been added to.

  Not every channel in the workspace: the app may post only where it has been
  invited, so a list of all of them -- hundreds, in a workspace of any size --
  was mostly choices that would fail, with the few that would not hidden among
  them. The server asks Slack for the app's own channels, and this says how to
  add another, because "where is #ops?" is the first thing somebody asks of a
  list that does not have it.

  Used wherever a channel is chosen: Send to Slack, a subscription to a
  channel, and an alert's destinations.
*/

export function useSlackChannels() {
  const [state, setState] = useState({ channels: null, appName: null, problem: null });

  useEffect(() => {
    let cancelled = false;
    axios
      .get("api/slack/channels")
      .then((data) => {
        if (!cancelled) setState({ channels: data.channels || [], appName: data.app_name || null, problem: null });
      })
      .catch((error) => {
        if (!cancelled) {
          // Slack's own reason, which is usually actionable: the app has been
          // removed, the token revoked, an administrator has not set it up.
          setState({
            channels: [],
            appName: null,
            problem: get(error, "response.data.message") || "Could not read the channel list from Slack.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

export function inviteCommand(appName) {
  return appName ? `/invite @${appName}` : "/invite and the app's name";
}

export default function SlackChannelSelect({ id, value, onChange, placeholder, className, ...rest }) {
  const { channels, appName, problem } = useSlackChannels();
  const loading = channels === null;
  const none = !loading && !problem && channels.length === 0;

  return (
    <>
      {problem && <Alert className="m-b-10" type="error" showIcon message={problem} />}
      <Select
        id={id}
        className={className}
        style={{ width: "100%" }}
        placeholder={loading ? "Asking Slack…" : none ? "The app is in no channel yet" : placeholder}
        loading={loading}
        disabled={none || !!problem}
        showSearch
        optionFilterProp="label"
        value={value}
        onChange={(channelId) => onChange(channelId, find(channels, { id: channelId }))}
        options={(channels || []).map((channel) => ({
          value: channel.id,
          label: channel.private ? `#${channel.name} (private)` : `#${channel.name}`,
        }))}
        {...rest}
      />
      {!problem && (
        <p className="text-muted m-t-5 m-b-0" style={{ fontSize: 12 }} data-test="SlackChannelHint">
          {none ? (
            <>
              The app has not been added to any channel. In Slack, open the channel and type{" "}
              <code>{inviteCommand(appName)}</code>, then come back here.
            </>
          ) : (
            <>
              Only channels the app has been added to are listed. To add one, type <code>{inviteCommand(appName)}</code>{" "}
              in it in Slack.
            </>
          )}
        </p>
      )}
    </>
  );
}

SlackChannelSelect.propTypes = {
  id: PropTypes.string,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  placeholder: PropTypes.string,
  className: PropTypes.string,
};

SlackChannelSelect.defaultProps = {
  id: undefined,
  value: undefined,
  placeholder: "Pick a channel",
  className: undefined,
};
