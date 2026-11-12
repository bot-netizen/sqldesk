import { without, find, get, includes, map, toLower } from "lodash";
import React from "react";
import PropTypes from "prop-types";

import Link from "@/components/Link";
import Button from "antd/lib/button";
import SelectItemsDialog from "@/components/SelectItemsDialog";
import { Destination as DestinationType, UserProfile as UserType } from "@/components/proptypes";

import DestinationService, { IMG_ROOT } from "@/services/destination";
import TypeLogo from "@/components/TypeLogo";
import AlertSubscription from "@/services/alert-subscription";
import { axios } from "@/services/axios";
import { clientConfig, currentUser } from "@/services/auth";
import SlackChannelSelect from "@/components/SlackChannelSelect";
import notification from "@/services/notification";
import ListItemAddon from "@/components/groups/ListItemAddon";
import EmailSettingsWarning from "@/components/EmailSettingsWarning";
import PlainButton from "@/components/PlainButton";
import Tooltip from "@/components/Tooltip";

import CloseOutlinedIcon from "@ant-design/icons/CloseOutlined";
import SlackOutlinedIcon from "@ant-design/icons/SlackOutlined";
import Switch from "antd/lib/switch";

import "./AlertDestinations.less";

const USER_EMAIL_DEST_ID = -1;

function normalizeSub(sub) {
  if (!sub.destination) {
    sub.destination = {
      id: USER_EMAIL_DEST_ID,
      name: sub.user.email,
      icon: "DEPRECATED",
      type: "email",
    };
  }
  return sub;
}

function ListItem({ destination: { name, type }, user, unsubscribe }) {
  const canUnsubscribe = currentUser.isAdmin || currentUser.id === user.id;

  return (
    <li className="destination-wrapper">
      <TypeLogo src={`${IMG_ROOT}/${type}.png`} label={name} className="destination-icon" alt={name} width={24} />
      <span className="flex-fill">{name}</span>
      {type === "email" && (
        <EmailSettingsWarning className="destination-warning" featureName="alert emails" mode="icon" />
      )}
      {canUnsubscribe && (
        <Tooltip title="Remove" mouseEnterDelay={0.5}>
          <PlainButton className="remove-button" onClick={unsubscribe}>
            {/* TODO: lacks visual feedback */}
            <CloseOutlinedIcon />
          </PlainButton>
        </Tooltip>
      )}
    </li>
  );
}

ListItem.propTypes = {
  destination: DestinationType.isRequired,
  user: UserType.isRequired,
  unsubscribe: PropTypes.func.isRequired,
};

export default class AlertDestinations extends React.Component {
  static propTypes = {
    alertId: PropTypes.any.isRequired,
  };

  state = {
    dests: [],
    subs: null,
  };

  componentDidMount() {
    const { alertId } = this.props;
    Promise.all([
      DestinationService.query(), // get all destinations
      AlertSubscription.query({ alertId }), // get subcriptions per alert
    ]).then(([dests, subs]) => {
      subs = subs.map(normalizeSub);
      this.setState({ dests, subs });
    });
  }

  showAddAlertSubDialog = () => {
    const { dests, subs } = this.state;

    SelectItemsDialog.showModal({
      width: 570,
      showCount: true,
      extraFooterContent: (
        <>
          <i className="fa fa-info-circle" aria-hidden="true" /> Create new destinations in{" "}
          <Tooltip title="Opens page in a new tab.">
            <Link href="destinations/new" target="_blank">
              Alert Destinations
            </Link>
          </Tooltip>
        </>
      ),
      dialogTitle: "Add Existing Alert Destinations",
      inputPlaceholder: "Search destinations...",
      searchItems: (searchTerm) => {
        searchTerm = toLower(searchTerm);
        return Promise.resolve(dests.filter((d) => includes(toLower(d.name), searchTerm)));
      },
      renderItem: (item, { isSelected }) => {
        const alreadyInGroup = !!find(subs, (s) => s.destination.id === item.id);

        return {
          content: (
            <div className="destination-wrapper">
              <TypeLogo
                src={`${IMG_ROOT}/${item.type}.png`}
                label={item.name}
                className="destination-icon"
                alt={item.name}
                width={24}
              />
              <span className="flex-fill">{item.name}</span>
              <ListItemAddon isSelected={isSelected} alreadyInGroup={alreadyInGroup} deselectedIcon="fa-plus" />
            </div>
          ),
          isDisabled: alreadyInGroup,
          className: isSelected || alreadyInGroup ? "selected" : "",
        };
      },
    }).onClose((items) => {
      const promises = map(items, (item) => this.subscribe(item));
      return Promise.all(promises)
        .then(() => {
          notification.success("Subscribed.");
        })
        .catch(() => {
          notification.error("Failed saving subscription.");
          return Promise.reject(null); // keep dialog visible but suppress its default error message
        });
    });
  };

  /*
    A Slack channel, picked rather than typed, and only from the channels the
    app is in. The server hands back that channel's destination -- the one
    other alerts to it already use, or a new one -- so nobody has to ask an
    administrator to make one first, or find it by name among the rest.
  */
  addSlackChannel = (channelId, channel) => {
    if (!channelId) {
      return;
    }
    axios
      .post("api/slack/destinations", { channel: channelId })
      .then((destination) => {
        const { dests, subs } = this.state;
        if (!find(dests, { id: destination.id })) {
          this.setState({ dests: [...dests, destination] });
        }
        const name = channel ? `#${channel.name}` : destination.name;
        if (find(subs, (s) => s.destination.id === destination.id)) {
          notification.info(`This alert already posts to ${name}.`);
          return null;
        }
        return this.subscribe(destination).then(() => notification.success(`This alert will post to ${name}.`));
      })
      .catch((error) => {
        notification.error(get(error, "response.data.message") || "Could not add that channel.");
      });
  };

  onUserEmailToggle = (sub) => {
    if (sub) {
      this.unsubscribe(sub);
    } else {
      this.subscribe();
    }
  };

  subscribe = (dest) => {
    const { alertId } = this.props;

    const sub = { alert_id: alertId };
    if (dest) {
      sub.destination_id = dest.id;
    }

    return AlertSubscription.create(sub).then((sub) => {
      const { subs } = this.state;
      this.setState({
        subs: [...subs, normalizeSub(sub)],
      });
    });
  };

  unsubscribe = (sub) => {
    AlertSubscription.delete(sub)
      .then(() => {
        // not showing subscribe notification cause it's redundant here
        const { subs } = this.state;
        this.setState({
          subs: without(subs, sub),
        });
      })
      .catch(() => {
        notification.error("Failed unsubscribing.");
      });
  };

  render() {
    if (!this.props.alertId) {
      return null;
    }

    const { subs } = this.state;
    const currentUserEmailSub = find(subs, {
      destination: { id: USER_EMAIL_DEST_ID },
      user: { id: currentUser.id },
    });
    const filteredSubs = without(subs, currentUserEmailSub);
    const { mailSettingsMissing } = clientConfig;

    return (
      <div className="alert-destinations" data-test="AlertDestinations">
        <Tooltip title='Click to add an existing "Alert Destination"' mouseEnterDelay={0.5}>
          <Button
            data-test="ShowAddAlertSubDialog"
            type="primary"
            size="small"
            className="add-button"
            onClick={this.showAddAlertSubDialog}
          >
            <i className="fa fa-plus f-12 m-r-5" aria-hidden="true" /> Add
          </Button>
        </Tooltip>
        <ul>
          <li className="destination-wrapper">
            <i className="destination-icon fa fa-envelope" aria-hidden="true" />
            <span className="flex-fill">{currentUser.email}</span>
            <EmailSettingsWarning className="destination-warning" featureName="alert emails" mode="icon" />
            {!mailSettingsMissing && (
              <Switch
                size="small"
                className="toggle-button"
                checked={!!currentUserEmailSub}
                loading={!subs}
                onChange={() => this.onUserEmailToggle(currentUserEmailSub)}
                data-test="UserEmailToggle"
              />
            )}
          </li>
          {filteredSubs.map((s) => (
            <ListItem key={s.id} unsubscribe={() => this.unsubscribe(s)} {...s} />
          ))}
        </ul>
        {clientConfig.slackConfigured && (
          <div className="slack-channel-picker" data-test="AlertSlackChannel">
            <label htmlFor="alert-slack-channel" className="m-b-5 d-block">
              <SlackOutlinedIcon className="m-r-5" aria-hidden="true" />
              Post to a Slack channel
            </label>
            <SlackChannelSelect
              id="alert-slack-channel"
              value={undefined}
              placeholder="Pick a channel to add"
              onChange={this.addSlackChannel}
            />
          </div>
        )}
      </div>
    );
  }
}
