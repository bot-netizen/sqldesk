import { get, find, toUpper } from "lodash";
import React from "react";
import PropTypes from "prop-types";

import Modal from "antd/lib/modal";
import navigateTo from "@/components/ApplicationArea/navigateTo";
import LoadingState from "@/components/items-list/components/LoadingState";
import DynamicForm from "@/components/dynamic-form/DynamicForm";
import helper from "@/components/dynamic-form/dynamicFormHelper";
import HelpTrigger, { TYPES as HELP_TRIGGER_TYPES } from "@/components/HelpTrigger";
import wrapSettingsTab from "@/components/SettingsWrapper";

import DataSource, { IMG_ROOT } from "@/services/data-source";
import TypeLogo from "@/components/TypeLogo";
import notification from "@/services/notification";
import UploadedFilesPanel from "./UploadedFilesPanel";

const DESCRIPTION_FIELD = (dataSource) => ({
  name: "description",
  title: "Description",
  type: "textarea",
  required: false,
  initialValue: dataSource.description,
  contentAfter: React.createElement("hr"),
  placeholder: "What this source is for: which tables to prefer, what is untrusted, what a row means.",
  props: { rows: 3 },
});

/*
  Which queues this source's queries go on.

  Until now the only way to set these was an UPDATE against the `data_sources`
  table -- which the Administration page actually told people to run. Giving a
  slow warehouse a queue of its own is the single most useful thing an
  administrator can do to stop it starving everything else, and it should not
  require psql.

  In the extra fields rather than the main form: most sources never need it,
  and the ones that do are a deliberate decision somebody has gone looking for.
*/
const QUEUE_FIELDS = (dataSource) => [
  {
    name: "queue_name",
    title: "Queue",
    type: "text",
    required: false,
    extra: true,
    initialValue: dataSource.queue_name,
    placeholder: "queries",
    // Said here because the consequence of getting it wrong is silent: a
    // queue nothing serves is a data source whose queries wait forever.
    helpText:
      "A queue of this source's own, for a warehouse slow enough to starve the rest. A worker has to be running with this name in its QUEUES, or nothing here will run.",
  },
  {
    name: "scheduled_queue_name",
    title: "Scheduled queue",
    type: "text",
    required: false,
    extra: true,
    initialValue: dataSource.scheduled_queue_name,
    placeholder: "scheduled_queries",
    contentAfter: React.createElement("hr"),
    helpText:
      "The same, for this source's scheduled refreshes. Keeping them apart is what stops a refresh storm delaying somebody waiting at a dashboard.",
  },
];

const DEFAULT_QUEUES = { queue_name: "queries", scheduled_queue_name: "scheduled_queries" };

function hasOwnQueue(dataSource) {
  return Object.entries(DEFAULT_QUEUES).some(
    ([field, fallback]) => dataSource[field] && dataSource[field] !== fallback
  );
}

class EditDataSource extends React.Component {
  static propTypes = {
    dataSourceId: PropTypes.string.isRequired,
    onError: PropTypes.func,
  };

  static defaultProps = {
    onError: () => {},
  };

  state = {
    dataSource: null,
    type: null,
    loading: true,
  };

  componentDidMount() {
    DataSource.get({ id: this.props.dataSourceId })
      .then((dataSource) => {
        const { type } = dataSource;
        this.setState({ dataSource });
        DataSource.types().then((types) => this.setState({ type: find(types, { type }), loading: false }));
      })
      .catch((error) => this.props.onError(error));
  }

  saveDataSource = (values, successCallback, errorCallback) => {
    const { dataSource } = this.state;
    helper.updateTargetWithValues(dataSource, values, ["name", "description", "queue_name", "scheduled_queue_name"]);
    DataSource.save(dataSource)
      .then(() => successCallback("Saved."))
      .catch((error) => {
        const message = get(error, "response.data.message", "Failed saving.");
        errorCallback(message);
      });
  };

  deleteDataSource = (callback) => {
    const { dataSource } = this.state;

    const doDelete = () => {
      DataSource.delete(dataSource)
        .then(() => {
          notification.success("Data source deleted successfully.");
          navigateTo("data_sources");
        })
        .catch(() => {
          callback();
        });
    };

    Modal.confirm({
      title: "Delete Data Source",
      content: "Are you sure you want to delete this data source?",
      okText: "Delete",
      okType: "danger",
      onOk: doDelete,
      onCancel: callback,
      maskClosable: true,
      autoFocusButton: null,
    });
  };

  testConnection = (callback) => {
    const { dataSource } = this.state;
    DataSource.test({ id: dataSource.id })
      .then((httpResponse) => {
        if (httpResponse.ok) {
          notification.success("Success");
        } else {
          notification.error("Connection Test Failed:", httpResponse.message, { duration: 10 });
        }
        callback();
      })
      .catch(() => {
        notification.error(
          "Connection Test Failed:",
          "Unknown error occurred while performing connection test. Please try again later.",
          { duration: 10 }
        );
        callback();
      });
  };

  renderForm() {
    const { dataSource, type } = this.state;
    // Shown on the data source form and nowhere else: it is a column on this
    // row, while a destination of the same shape has no such thing.
    const fields = helper.getFields(type, dataSource, [DESCRIPTION_FIELD(dataSource), ...QUEUE_FIELDS(dataSource)]);
    const helpTriggerType = `DS_${toUpper(type.type)}`;
    const formProps = {
      fields,
      type,
      actions: [
        { name: "Delete", type: "danger", callback: this.deleteDataSource },
        { name: "Test Connection", pullRight: true, callback: this.testConnection, disableWhenDirty: true },
      ],
      onSubmit: this.saveDataSource,
      feedbackIcons: true,
      // A queue somebody has *changed* counts as a filled extra field, so the
      // section is already open when they come back to it. Compared against
      // the defaults rather than merely being set: every data source carries
      // "queries", so truthiness would open the section for all of them.
      defaultShowExtraFields: helper.hasFilledExtraField(type, dataSource) || hasOwnQueue(dataSource),
    };

    return (
      <div className="row" data-test="DataSource">
        <div className="text-right m-r-10">
          {HELP_TRIGGER_TYPES[helpTriggerType] && (
            <HelpTrigger className="f-13" type={helpTriggerType}>
              Setup Instructions <i className="fa fa-question-circle" aria-hidden="true" />
              <span className="sr-only">(help)</span>
            </HelpTrigger>
          )}
        </div>
        <div className="text-center m-b-10">
          <TypeLogo className="p-5" src={`${IMG_ROOT}/${type.type}.png`} label={type.type} alt={type.name} width={64} />
          <h3 className="m-0">{type.name}</h3>
        </div>
        <div className="col-md-4 col-md-offset-4 m-b-10">
          <DynamicForm {...formProps} />
          {type.type === "duckdb" && <UploadedFilesPanel dataSourceId={dataSource.id} />}
        </div>
      </div>
    );
  }

  render() {
    return this.state.loading ? <LoadingState className="" /> : this.renderForm();
  }
}

const EditDataSourcePage = wrapSettingsTab(EditDataSource);

export default EditDataSourcePage;
