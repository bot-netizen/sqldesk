import React from "react";
import PropTypes from "prop-types";
import { isEmpty, toUpper, includes, get, uniqueId } from "lodash";
import Button from "antd/lib/button";
import List from "antd/lib/list";
import Modal from "antd/lib/modal";
import Input from "antd/lib/input";
import Steps from "antd/lib/steps";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import Link from "@/components/Link";
import { PreviewCard } from "@/components/PreviewCard";
import EmptyState from "@/components/items-list/components/EmptyState";
import DynamicForm from "@/components/dynamic-form/DynamicForm";
import helper from "@/components/dynamic-form/dynamicFormHelper";
import HelpTrigger, { TYPES as HELP_TRIGGER_TYPES } from "@/components/HelpTrigger";
import Uploads from "@/services/uploads";
import notification from "@/services/notification";

// Data source types that skip the configuration form entirely: selecting the
// type immediately opens a native file picker, and the data source is created
// (with sane defaults) and the file uploaded to it in one motion.
const FILE_UPLOAD_TYPES = ["duckdb"];

const { Step } = Steps;
const { Search } = Input;

const StepEnum = {
  SELECT_TYPE: 0,
  CONFIGURE_IT: 1,
  DONE: 2,
};

class CreateSourceDialog extends React.Component {
  static propTypes = {
    dialog: DialogPropType.isRequired,
    types: PropTypes.arrayOf(PropTypes.object),
    sourceType: PropTypes.string.isRequired,
    imageFolder: PropTypes.string.isRequired,
    helpTriggerPrefix: PropTypes.string,
    onCreate: PropTypes.func.isRequired,
  };

  static defaultProps = {
    types: [],
    helpTriggerPrefix: null,
  };

  state = {
    searchText: "",
    selectedType: null,
    savingSource: false,
    currentStep: StepEnum.SELECT_TYPE,
    pendingFile: null,
    uploadName: "",
  };

  formId = uniqueId("sourceForm");

  fileInputRef = React.createRef();

  selectType = (selectedType) => {
    if (includes(FILE_UPLOAD_TYPES, selectedType.type)) {
      this.setState({ selectedType }, () => this.fileInputRef.current.click());
      return;
    }
    this.setState({ selectedType, currentStep: StepEnum.CONFIGURE_IT });
  };

  resetType = () => {
    if (this.state.currentStep === StepEnum.CONFIGURE_IT) {
      this.setState({
        searchText: "",
        selectedType: null,
        currentStep: StepEnum.SELECT_TYPE,
        pendingFile: null,
        uploadName: "",
      });
    }
  };

  handleFileSelected = (e) => {
    const file = e.target.files[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) {
      return;
    }

    const derivedName = file.name.replace(/\.[^./]+$/, "") || "Uploaded File";
    this.setState({ pendingFile: file, uploadName: derivedName, currentStep: StepEnum.CONFIGURE_IT });
  };

  confirmFileUpload = () => {
    const { selectedType, savingSource, pendingFile, uploadName } = this.state;
    if (savingSource || !pendingFile || !uploadName.trim()) {
      return;
    }

    this.setState({ savingSource: true, currentStep: StepEnum.DONE });
    this.props
      .onCreate(selectedType, { name: uploadName.trim(), dbpath: ":memory:" })
      .then((dataSource) => Uploads.upload(dataSource.id, pendingFile, uploadName.trim()).then(() => dataSource))
      .then((dataSource) => {
        this.props.dialog.close({ success: true, data: dataSource });
      })
      .catch((error) => {
        this.setState({ savingSource: false, currentStep: StepEnum.CONFIGURE_IT });
        notification.error(get(error, "response.data.message", "Failed to upload file."));
      });
  };

  isFileUploadFlow() {
    return includes(FILE_UPLOAD_TYPES, get(this.state.selectedType, "type"));
  }

  createSource = (values, successCallback, errorCallback) => {
    const { selectedType, savingSource } = this.state;
    if (!savingSource) {
      this.setState({ savingSource: true, currentStep: StepEnum.DONE });
      this.props
        .onCreate(selectedType, values)
        .then((data) => {
          successCallback("Saved.");
          this.props.dialog.close({ success: true, data });
        })
        .catch((error) => {
          this.setState({ savingSource: false, currentStep: StepEnum.CONFIGURE_IT });
          errorCallback(get(error, "response.data.message", "Failed saving."));
        });
    }
  };

  renderTypeSelector() {
    const { types } = this.props;
    const { searchText } = this.state;
    const filteredTypes = types.filter(
      (type) => isEmpty(searchText) || includes(type.name.toLowerCase(), searchText.toLowerCase())
    );
    return (
      <div className="m-t-10">
        <Search
          placeholder="Search..."
          aria-label="Search"
          onChange={(e) => this.setState({ searchText: e.target.value })}
          autoFocus
          data-test="SearchSource"
        />
        <div className="scrollbox p-5 m-t-10" style={{ minHeight: "30vh", maxHeight: "40vh" }}>
          {isEmpty(filteredTypes) ? (
            <EmptyState className="" />
          ) : (
            <List size="small" dataSource={filteredTypes} renderItem={(item) => this.renderItem(item)} />
          )}
        </div>
      </div>
    );
  }

  renderForm() {
    const { imageFolder, helpTriggerPrefix } = this.props;
    const { selectedType } = this.state;
    const fields = helper.getFields(selectedType);
    const helpTriggerType = `${helpTriggerPrefix}${toUpper(selectedType.type)}`;
    return (
      <div>
        <div className="d-flex justify-content-center align-items-center">
          <img className="p-5" src={`${imageFolder}/${selectedType.type}.png`} alt={selectedType.name} width="48" />
          <h4 className="m-0">{selectedType.name}</h4>
        </div>
        <div className="text-right">
          {HELP_TRIGGER_TYPES[helpTriggerType] && (
            <HelpTrigger className="f-13" type={helpTriggerType}>
              Setup Instructions <i className="fa fa-question-circle" aria-hidden="true" />
              <span className="sr-only">(help)</span>
            </HelpTrigger>
          )}
        </div>
        <DynamicForm id={this.formId} fields={fields} onSubmit={this.createSource} feedbackIcons hideSubmitButton />
        {selectedType.type === "databricks" && (
          <small>
            By using the Databricks Data Source you agree to the Databricks JDBC/ODBC{" "}
            <Link href="https://databricks.com/spark/odbc-driver-download" target="_blank" rel="noopener noreferrer">
              Driver Download Terms and Conditions
            </Link>
            .
          </small>
        )}
      </div>
    );
  }

  renderFileUploadNamePrompt() {
    const { imageFolder } = this.props;
    const { selectedType, pendingFile, uploadName } = this.state;
    return (
      <div>
        <div className="d-flex justify-content-center align-items-center">
          <img className="p-5" src={`${imageFolder}/${selectedType.type}.png`} alt={selectedType.name} width="48" />
          <h4 className="m-0">{selectedType.name}</h4>
        </div>
        <div className="m-t-15 m-b-5">
          <label htmlFor="uploadName">Name</label>
        </div>
        <Input
          id="uploadName"
          value={uploadName}
          onChange={(e) => this.setState({ uploadName: e.target.value })}
          onPressEnter={this.confirmFileUpload}
          autoFocus
          data-test="UploadNameInput"
        />
        <p className="text-muted m-t-10">
          <i className="fa fa-file-o m-r-5" aria-hidden="true" />
          {pendingFile.name}
        </p>
      </div>
    );
  }

  renderUploading() {
    const { pendingFile } = this.state;
    return (
      <div className="text-center p-l-15 p-r-15" style={{ minHeight: "30vh" }}>
        <div className="p-t-15 p-b-15">
          <i className="fa fa-spinner fa-pulse fa-2x" aria-hidden="true" />
        </div>
        <p>Uploading {get(pendingFile, "name")}&hellip;</p>
      </div>
    );
  }

  renderItem(item) {
    const { imageFolder } = this.props;
    return (
      <List.Item className="p-l-10 p-r-10 clickable" onClick={() => this.selectType(item)}>
        <PreviewCard
          title={item.name}
          imageUrl={`${imageFolder}/${item.type}.png`}
          roundedImage={false}
          data-test="PreviewItem"
          data-test-type={item.type}
        >
          <i className="fa fa-angle-double-right" aria-hidden="true" />
        </PreviewCard>
      </List.Item>
    );
  }

  renderFooter() {
    const { currentStep, savingSource, uploadName } = this.state;
    const { dialog } = this.props;
    const isFileUploadFlow = this.isFileUploadFlow();

    if (currentStep === StepEnum.SELECT_TYPE) {
      return [
        <Button key="cancel" onClick={() => dialog.dismiss()} data-test="CreateSourceCancelButton">
          Cancel
        </Button>,
        <Button key="submit" type="primary" disabled>
          Create
        </Button>,
      ];
    }

    if (isFileUploadFlow && currentStep === StepEnum.DONE) {
      return [
        <Button key="submit" type="primary" loading disabled>
          Uploading&hellip;
        </Button>,
      ];
    }

    if (isFileUploadFlow && currentStep === StepEnum.CONFIGURE_IT) {
      return [
        <Button key="previous" onClick={this.resetType}>
          Previous
        </Button>,
        <Button
          key="submit"
          type="primary"
          disabled={!uploadName.trim()}
          loading={savingSource}
          onClick={this.confirmFileUpload}
          data-test="CreateSourceSaveButton"
        >
          Create
        </Button>,
      ];
    }

    return [
      <Button key="previous" onClick={this.resetType}>
        Previous
      </Button>,
      <Button
        key="submit"
        htmlType="submit"
        form={this.formId}
        type="primary"
        loading={savingSource}
        data-test="CreateSourceSaveButton"
      >
        Create
      </Button>,
    ];
  }

  render() {
    const { currentStep } = this.state;
    const { dialog, sourceType } = this.props;
    const isFileUploadFlow = this.isFileUploadFlow();
    return (
      <Modal {...dialog.props} title={`Create a New ${sourceType}`} footer={this.renderFooter()}>
        <div data-test="CreateSourceDialog">
          <input
            ref={this.fileInputRef}
            type="file"
            accept=".csv,.parquet"
            style={{ display: "none" }}
            onChange={this.handleFileSelected}
            data-test="CreateSourceFileInput"
          />
          <Steps className="hidden-xs m-b-10" size="small" current={currentStep} progressDot>
            {currentStep === StepEnum.CONFIGURE_IT ? (
              <Step title={<a>Type Selection</a>} className="clickable" onClick={this.resetType} />
            ) : (
              <Step title="Type Selection" />
            )}
            <Step title="Configuration" />
            <Step title="Done" />
          </Steps>
          {currentStep === StepEnum.SELECT_TYPE && this.renderTypeSelector()}
          {currentStep === StepEnum.CONFIGURE_IT && isFileUploadFlow && this.renderFileUploadNamePrompt()}
          {currentStep === StepEnum.CONFIGURE_IT && !isFileUploadFlow && this.renderForm()}
          {currentStep === StepEnum.DONE && isFileUploadFlow && this.renderUploading()}
          {currentStep === StepEnum.DONE && !isFileUploadFlow && this.renderForm()}
        </div>
      </Modal>
    );
  }
}

export default wrapDialog(CreateSourceDialog);
