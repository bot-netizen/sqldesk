import { extend, map, filter, reduce } from "lodash";
import React, { useMemo } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Tag from "antd/lib/tag";
import EllipsisOutlinedIcon from "@ant-design/icons/EllipsisOutlined";
import useMedia from "use-media";
import Link from "@/components/Link";
import Tooltip from "@/components/Tooltip";
import EditInPlace from "@/components/EditInPlace";
import FavoritesControl from "@/components/FavoritesControl";
import { QueryTagsControl } from "@/components/tags-control/TagsControl";
import getTags from "@/services/getTags";
import { clientConfig } from "@/services/auth";
import useQueryFlags from "../hooks/useQueryFlags";
import useArchiveQuery from "../hooks/useArchiveQuery";
import usePublishQuery from "../hooks/usePublishQuery";
import useUnpublishQuery from "../hooks/useUnpublishQuery";
import useUpdateQueryTags from "../hooks/useUpdateQueryTags";
import useRenameQuery from "../hooks/useRenameQuery";
import useDuplicateQuery from "../hooks/useDuplicateQuery";
import useApiKeyDialog from "../hooks/useApiKeyDialog";
import usePermissionsEditorDialog from "../hooks/usePermissionsEditorDialog";
import useVerifyQuery from "../hooks/useVerifyQuery";
import useQueryHistoryDialog from "../hooks/useQueryHistoryDialog";

import "./QueryPageHeader.less";

function getQueryTags() {
  return getTags("api/queries/tags").then((tags) => map(tags, (t) => t.name));
}

function createMenu(menu) {
  const handlers = {};

  const groups = map(menu, (group) =>
    filter(
      map(group, (props, key) => {
        props = extend({ isAvailable: true, isEnabled: true, onClick: () => {} }, props);
        if (props.isAvailable) {
          handlers[key] = props.onClick;
          return (
            <Menu.Item key={key} disabled={!props.isEnabled}>
              {props.title}
            </Menu.Item>
          );
        }
        return null;
      })
    )
  );

  return (
    <Menu onClick={({ key }) => handlers[key]()}>
      {reduce(
        filter(groups, (group) => group.length > 0),
        (result, items, key) => {
          const divider = result.length > 0 ? <Menu.Divider key={`divider${key}`} /> : null;
          return [...result, divider, ...items];
        },
        []
      )}
    </Menu>
  );
}

export default function QueryPageHeader({
  query,
  dataSource,
  sourceMode,
  selectedVisualization,
  headerExtra,
  tagsExtra,
  onChange,
  onSaved,
  isDirty,
}) {
  const isDesktop = useMedia({ minWidth: 768 });
  const queryFlags = useQueryFlags(query, dataSource);
  const updateName = useRenameQuery(query, onChange);
  const updateTags = useUpdateQueryTags(query, onChange);
  const archiveQuery = useArchiveQuery(query, onChange);
  const publishQuery = usePublishQuery(query, onChange);
  const unpublishQuery = useUnpublishQuery(query, onChange);
  const [isDuplicating, duplicateQuery] = useDuplicateQuery(query);
  const openApiKeyDialog = useApiKeyDialog(query, onChange);
  const openPermissionsEditorDialog = usePermissionsEditorDialog(query);
  const verifying = useVerifyQuery(query);
  // `onSaved` rather than `onChange`: a restore has already been written, so
  // the editor's idea of what is saved has to move with it.
  const openHistoryDialog = useQueryHistoryDialog(query, queryFlags.canEdit, onSaved || onChange, isDirty);

  const moreActionsMenu = useMemo(
    () =>
      createMenu([
        {
          fork: {
            isEnabled: !queryFlags.isNew && queryFlags.canFork && !isDuplicating,
            title: (
              <React.Fragment>
                Fork <i className="fa fa-external-link m-l-5" aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </React.Fragment>
            ),
            onClick: duplicateQuery,
          },
        },
        {
          archive: {
            isAvailable: !queryFlags.isNew && queryFlags.canEdit && !queryFlags.isArchived,
            title: "Archive",
            onClick: archiveQuery,
          },
          managePermissions: {
            isAvailable:
              !queryFlags.isNew && queryFlags.canEdit && !queryFlags.isArchived && clientConfig.showPermissionsControl,
            title: "Manage Permissions",
            onClick: openPermissionsEditorDialog,
          },
          publish: {
            isAvailable:
              !isDesktop && queryFlags.isDraft && !queryFlags.isArchived && !queryFlags.isNew && queryFlags.canEdit,
            title: "Publish",
            onClick: publishQuery,
          },
          unpublish: {
            isAvailable: !clientConfig.disablePublish && !queryFlags.isNew && queryFlags.canEdit && !queryFlags.isDraft,
            title: "Unpublish",
            onClick: unpublishQuery,
          },
        },
        {
          // A curator confirms a query here rather than from a list, because
          // confirming is reading the SQL and saying yes -- and this is the
          // page where the SQL is on screen. Hidden entirely for anyone
          // without the feature: it is not a thing to be told you cannot do.
          confirmAnswer: {
            isAvailable: !queryFlags.isNew && !queryFlags.isArchived && verifying.canVerify,
            // Three states, because "confirmed" and "confirmed, then edited"
            // are different situations and only one of them is a job.
            title: !verifying.verification
              ? "Confirm as the right answer"
              : verifying.verification.current
                ? "Edit what it answers"
                : "Confirm again \u2014 the SQL has changed",
            onClick: verifying.confirm,
          },
          withdrawAnswer: {
            isAvailable: !queryFlags.isNew && verifying.canVerify && !!verifying.verification,
            title: "No longer the right answer",
            onClick: verifying.withdraw,
          },
        },
        {
          // Reading what a query used to say needs nothing but being able to
          // read the query; the dialog offers the restore only to somebody who
          // could have made the same edit by hand.
          history: {
            isAvailable: !queryFlags.isNew,
            title: "History",
            onClick: openHistoryDialog,
          },
        },
        {
          showAPIKey: {
            // The key is a credential that outlives group membership, so the
            // server hands it only to people who may also regenerate it.
            isAvailable: !clientConfig.disablePublicUrls && !queryFlags.isNew && queryFlags.canEdit,
            title: "Show API Key",
            onClick: openApiKeyDialog,
          },
        },
      ]),
    [
      queryFlags.isNew,
      queryFlags.canFork,
      queryFlags.canEdit,
      queryFlags.isArchived,
      queryFlags.isDraft,
      isDuplicating,
      duplicateQuery,
      archiveQuery,
      openPermissionsEditorDialog,
      isDesktop,
      publishQuery,
      unpublishQuery,
      openApiKeyDialog,
      openHistoryDialog,
      verifying.canVerify,
      verifying.verification,
      verifying.confirm,
      verifying.withdraw,
    ]
  );

  return (
    <div className="query-page-header">
      <div className="title-with-tags">
        <div className="page-title">
          <div className="d-flex align-items-center">
            {!queryFlags.isNew && <FavoritesControl item={query} />}
            <h3>
              <EditInPlace isEditable={queryFlags.canEdit} onDone={updateName} ignoreBlanks value={query.name} />
            </h3>
          </div>
        </div>
        <div className="query-tags">
          <QueryTagsControl
            tags={query.tags}
            isDraft={queryFlags.isDraft}
            isArchived={queryFlags.isArchived}
            canEdit={queryFlags.canEdit}
            getAvailableTags={getQueryTags}
            onEdit={updateTags}
            tagsExtra={
              <React.Fragment>
                {verifying.verification && (
                  <Tooltip
                    title={
                      verifying.verification.current
                        ? "A curator has read this and confirmed it answers its question. AI clients are told to prefer it."
                        : "This was confirmed, but the SQL has changed since. Nothing is being told it is confirmed."
                    }
                  >
                    <Tag color={verifying.verification.current ? "green" : "orange"}>
                      {verifying.verification.current ? "confirmed" : "edited since confirmed"}
                    </Tag>
                  </Tooltip>
                )}
                {tagsExtra}
              </React.Fragment>
            }
          />
        </div>
      </div>
      <div className="header-actions">
        {headerExtra}
        {isDesktop && queryFlags.isDraft && !queryFlags.isArchived && !queryFlags.isNew && queryFlags.canEdit && (
          <Button className="m-r-5" onClick={publishQuery}>
            <i className="fa fa-paper-plane m-r-5" aria-hidden="true" /> Publish
          </Button>
        )}

        {!queryFlags.isNew && queryFlags.canViewSource && (
          <span>
            {!sourceMode && (
              <Link.Button className="m-r-5" href={query.getUrl(true, selectedVisualization)}>
                <i className="fa fa-pencil-square-o" aria-hidden="true" />
                <span className="m-l-5">Edit Source</span>
              </Link.Button>
            )}
            {sourceMode && (
              <Link.Button
                className="m-r-5"
                href={query.getUrl(false, selectedVisualization)}
                data-test="QueryPageShowResultOnly"
              >
                <i className="fa fa-table" aria-hidden="true" />
                <span className="m-l-5">Show Results Only</span>
              </Link.Button>
            )}
          </span>
        )}

        {!queryFlags.isNew && (
          <Dropdown overlay={moreActionsMenu} trigger={["click"]}>
            <Button data-test="QueryPageHeaderMoreButton" aria-label="More actions">
              <EllipsisOutlinedIcon rotate={90} aria-hidden="true" />
            </Button>
          </Dropdown>
        )}
      </div>
    </div>
  );
}

QueryPageHeader.propTypes = {
  query: PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
    name: PropTypes.string,
    tags: PropTypes.arrayOf(PropTypes.string),
  }).isRequired,
  dataSource: PropTypes.object,
  sourceMode: PropTypes.bool,
  selectedVisualization: PropTypes.number,
  headerExtra: PropTypes.node,
  tagsExtra: PropTypes.node,
  onChange: PropTypes.func,
  // The query as the server now holds it, for a change this header made that
  // was already written -- a restore. Falls back to `onChange` for the pages
  // with no editor to keep in step.
  onSaved: PropTypes.func,
  isDirty: PropTypes.bool,
};

QueryPageHeader.defaultProps = {
  dataSource: null,
  sourceMode: false,
  selectedVisualization: null,
  headerExtra: null,
  tagsExtra: null,
  onChange: () => {},
  isDirty: false,
};
