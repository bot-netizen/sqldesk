import React from "react";
import { reject } from "lodash";
import Link from "@/components/Link";
import { Shell, Header } from "@/components/items-list/components/ListPage";
import Paginator from "@/components/Paginator";
import EmptyState from "@/components/empty-state/EmptyState";
import { wrap as itemsList, ControllerType } from "@/components/items-list/ItemsList";
import { ResourceItemsSource } from "@/components/items-list/classes/ItemsSource";
import { StateStorage } from "@/components/items-list/classes/StateStorage";
import ItemsTable, { Columns } from "@/components/items-list/components/ItemsTable";
import ListItemActions from "@/components/items-list/components/ListItemActions";
import { SearchControl } from "@/components/items-list/components/ListPageControls";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";
import navigateTo from "@/components/ApplicationArea/navigateTo";

import Notebook from "@/services/notebook";
import { currentUser } from "@/services/auth";

/*
  The notebooks somebody may see.

  A draft is the author's own -- the same promise queries and dashboards make,
  and enforced on the server rather than hidden here, so somebody cannot see
  another person's unfinished work by asking the API directly.
*/
/*
  The data source step stays -- a SQL cell queries one, so it genuinely is the
  first thing needed. The query step goes: a notebook is not a saved query, and
  telling somebody looking at an empty notebook list to go and write a query
  sends them to the wrong page.
*/
function dropTheQueryStep(steps) {
  return reject(steps, { key: "queries" });
}

class NotebookList extends React.Component {
  static propTypes = {
    controller: ControllerType.isRequired,
  };

  listColumns = [
    Columns.custom.sortable(
      (text, notebook) => (
        <span className="list-page-name">
          <Link className="table-main-title" href={`notebooks/${notebook.id}`} data-test="NotebookLink">
            {notebook.name}
          </Link>
          {notebook.is_draft && <span className="label label-default m-l-10">Draft</span>}
        </span>
      ),
      { title: "Name", field: "name" }
    ),
    Columns.custom((text, notebook) => (notebook.user ? notebook.user.name : null), {
      title: "Created By",
      width: "1%",
    }),
    Columns.timeAgo.sortable({ title: "Last Updated At", field: "updated_at", width: "1%" }),
    Columns.dateTime.sortable({ title: "Created At", field: "created_at", width: "1%" }),
    Columns.custom(
      (text, notebook) =>
        notebook.can_edit ? (
          <ListItemActions
            item={notebook}
            deleteLabel="Archive"
            deleteConfirm={{
              title: "Archive notebook",
              content: (
                <>
                  <p>“{notebook.name}” stays readable: its cells, its runs and the output on the page are kept.</p>
                  <p>
                    What goes is the handoff between its cells, which re-running rebuilds — so an archived notebook
                    keeps no data of its own.
                  </p>
                </>
              ),
              okText: "Archive",
            }}
            onDelete={(item) => Notebook.archive(item.id).then(() => this.props.controller.update())}
          />
        ) : null,
      { title: "", width: "1%", className: "p-l-0" }
    ),
  ];

  createNotebook = () => {
    Notebook.create({ name: "New Notebook" }).then((notebook) => navigateTo(`notebooks/${notebook.id}`));
  };

  render() {
    const { controller } = this.props;
    const subtitle = controller.isLoaded
      ? `${controller.totalItemsCount} ${controller.totalItemsCount === 1 ? "notebook" : "notebooks"}`
      : "Loading…";

    return (
      <div className="page-notebooks-list">
        <Shell>
          <Header title={controller.params.pageTitle} subtitle={subtitle}>
            <SearchControl
              value={controller.searchTerm}
              onChange={controller.updateSearch}
              placeholder="Search notebooks…"
              label="Search notebooks"
            />
            {currentUser.can("use_notebooks") && (
              <Link.Button type="primary" onClick={this.createNotebook} data-test="NewNotebookButton">
                <i className="fa fa-plus m-r-5" aria-hidden="true" />
                New notebook
              </Link.Button>
            )}
          </Header>

          {controller.isLoaded && controller.isEmpty ? (
            <EmptyState
              icon="fa fa-book"
              illustration="query"
              description="Chain SQL and Python together, where a saved query ends in one SELECT"
              helpMessage="A notebook starts with a SQL cell. A code cell reads what that fetched."
              getStepsItems={dropTheQueryStep}
            />
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

const NotebookListPage = itemsList(
  NotebookList,
  () =>
    new ResourceItemsSource({
      getResource() {
        return Notebook.all;
      },
      getRequest(unused, { page, itemsPerPage }) {
        return { page, page_size: itemsPerPage };
      },
    }),
  () => new StateStorage({ orderByField: "updated_at", orderByReverse: true, itemsPerPage: 20 })
);

routes.register(
  "Notebooks.List",
  routeWithUserSession({
    path: "/notebooks",
    title: "Notebooks",
    render: (pageProps) => <NotebookListPage {...pageProps} currentPage="notebooks" />,
  })
);

export default NotebookListPage;
