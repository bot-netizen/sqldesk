import { toUpper } from "lodash";
import React from "react";
import Link from "@/components/Link";
import { Shell, Header } from "@/components/items-list/components/ListPage";
import Paginator from "@/components/Paginator";
import EmptyState, { EmptyStateHelpMessage } from "@/components/empty-state/EmptyState";
import { wrap as itemsList, ControllerType } from "@/components/items-list/ItemsList";
import { ResourceItemsSource } from "@/components/items-list/classes/ItemsSource";
import { StateStorage } from "@/components/items-list/classes/StateStorage";
import DynamicComponent from "@/components/DynamicComponent";

import ItemsTable, { Columns } from "@/components/items-list/components/ItemsTable";
import ListItemActions from "@/components/items-list/components/ListItemActions";
import { SearchControl } from "@/components/items-list/components/ListPageControls";

import Alert from "@/services/alert";
import { currentUser } from "@/services/auth";

export const STATE_CLASS = {
  unknown: "label-warning",
  ok: "label-success",
  triggered: "label-danger",
};

class AlertsList extends React.Component {
  static propTypes = {
    controller: ControllerType.isRequired,
  };

  listColumns = [
    Columns.custom.sortable(
      (text, alert) => (
        <span title={alert.options.muted ? "Muted" : "Active"}>
          <i className={`fa fa-bell-${alert.options.muted ? "slash" : "o"} p-r-0`} aria-hidden="true" />
          <span className="sr-only">{alert.options.muted ? "Muted" : "Active"}</span>
        </span>
      ),
      {
        title: (
          <>
            <i className="fa fa-bell p-r-0" aria-hidden="true" />
            <span className="sr-only">Sort by notification status.</span>
          </>
        ),
        field: "muted",
        width: "1%",
      }
    ),
    Columns.custom.sortable(
      (text, alert) => (
        <span className="list-page-name">
          <Link className="table-main-title" href={"alerts/" + alert.id}>
            {alert.name}
          </Link>
        </span>
      ),
      {
        title: "Name",
        field: "name",
      }
    ),
    Columns.custom((text, item) => item.user.name, { title: "Created By", width: "1%" }),
    Columns.custom.sortable(
      (text, alert) => (
        <div>
          <span className={`label ${STATE_CLASS[alert.state]}`}>{toUpper(alert.state)}</span>
        </div>
      ),
      {
        title: "State",
        field: "state",
        width: "1%",
        className: "text-nowrap",
      }
    ),
    // An alert that went off six times reads very differently from one that
    // went off once and stayed there, and the state label cannot tell them
    // apart. Blank rather than "0" where it has been quiet: a column of
    // zeroes is noise, and the ones worth seeing should be the ones with ink.
    Columns.custom.sortable(
      (text, alert) =>
        alert.fires_24h > 0 ? (
          <Link
            className="alert-fires"
            href={"alerts/" + alert.id}
            title={`Fired ${alert.fires_24h} ${alert.fires_24h === 1 ? "time" : "times"} in the last 24 hours`}
          >
            {alert.fires_24h}
            <span className="sr-only"> {alert.fires_24h === 1 ? "time" : "times"} in the last 24 hours</span>
          </Link>
        ) : null,
      {
        title: "Fires (24h)",
        field: "fires_24h",
        width: "1%",
        className: "text-nowrap",
      }
    ),
    Columns.timeAgo.sortable({ title: "Last Updated At", field: "updated_at", width: "1%" }),
    Columns.dateTime.sortable({ title: "Created At", field: "created_at", width: "1%" }),
    // No permissions entry: ACLs exist for queries and dashboards only
    // (sqldesk/handlers/permissions.py maps just those two types), so an
    // alert has no sharing to manage.
    Columns.custom(
      (text, alert) => (
        <ListItemActions
          item={alert}
          editUrl={`alerts/${alert.id}/edit`}
          deleteLabel="Delete"
          deleteConfirm={{
            title: "Delete Alert",
            content: `Are you sure you want to delete the "${alert.name}" alert?`,
            okText: "Delete",
          }}
          onDelete={(item) => Alert.delete({ id: item.id }).then(() => this.props.controller.update())}
        />
      ),
      { title: "", width: "1%", className: "p-l-0" }
    ),
  ];

  render() {
    const { controller } = this.props;

    const subtitle = controller.isLoaded
      ? `${controller.totalItemsCount} ${controller.totalItemsCount === 1 ? "alert" : "alerts"}`
      : "Loading…";

    return (
      <div className="page-alerts-list">
        <Shell>
          <Header title={controller.params.pageTitle} subtitle={subtitle}>
            <SearchControl
              value={controller.searchTerm}
              onChange={controller.updateSearch}
              placeholder="Search alerts…"
              label="Search alerts"
            />
            {currentUser.hasPermission("list_alerts") && (
              <Link.Button type="primary" href="alerts/new">
                <i className="fa fa-plus m-r-5" aria-hidden="true" />
                New alert
              </Link.Button>
            )}
          </Header>

          {controller.isLoaded && controller.isEmpty ? (
            <DynamicComponent name="AlertsList.EmptyState">
              <EmptyState
                icon="fa fa-bell-o"
                illustration="alert"
                description="Get notified on certain events"
                helpMessage={<EmptyStateHelpMessage helpTriggerType="ALERTS" />}
                showAlertStep
              />
            </DynamicComponent>
          ) : (
            <div className="table-responsive bg-white tiled">
              <ItemsTable
                loading={!controller.isLoaded}
                items={controller.pageItems}
                columns={this.listColumns}
                orderByField={controller.orderByField}
                orderByReverse={controller.orderByReverse}
                toggleSorting={controller.toggleSorting}
              />
              <Paginator
                showPageSizeSelect
                totalCount={controller.totalItemsCount}
                pageSize={controller.itemsPerPage}
                onPageSizeChange={(itemsPerPage) => controller.updatePagination({ itemsPerPage })}
                page={controller.page}
                onChange={(page) => controller.updatePagination({ page })}
              />
            </div>
          )}
        </Shell>
      </div>
    );
  }
}

const AlertsListPage = itemsList(
  AlertsList,
  () =>
    new ResourceItemsSource({
      isPlainList: true,
      getRequest() {
        return {};
      },
      getResource() {
        return Alert.query.bind(Alert);
      },
      // The endpoint takes no `q` and returns every alert the person can see,
      // so the filtering happens in the browser over the whole list. The
      // query's name is searched as well as the alert's: an alert is usually
      // remembered by what it watches rather than by what somebody named it.
      matches(alert, term) {
        const fields = [alert.name, alert.query && alert.query.name];
        return fields.some((field) => typeof field === "string" && field.toLowerCase().includes(term));
      },
    }),
  () => new StateStorage({ orderByField: "created_at", orderByReverse: true, itemsPerPage: 20 })
);

export default AlertsListPage;
