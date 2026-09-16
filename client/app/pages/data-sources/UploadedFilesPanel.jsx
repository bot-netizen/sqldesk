import { get } from "lodash";
import React from "react";
import PropTypes from "prop-types";

import Button from "antd/lib/button";
import Input from "antd/lib/input";
import List from "antd/lib/list";
import Modal from "antd/lib/modal";
import Popconfirm from "antd/lib/popconfirm";

import Uploads from "@/services/uploads";
import notification from "@/services/notification";

function formatSize(bytes) {
  if (!bytes) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

class UploadedFilesPanel extends React.Component {
  static propTypes = {
    dataSourceId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  };

  state = {
    files: [],
    loading: true,
    uploading: false,
    pendingFile: null,
    uploadName: "",
  };

  fileInputRef = React.createRef();

  componentDidMount() {
    this.loadFiles();
  }

  loadFiles = () => {
    this.setState({ loading: true });
    Uploads.query(this.props.dataSourceId)
      .then((files) => this.setState({ files, loading: false }))
      .catch(() => this.setState({ loading: false }));
  };

  handleFileSelected = (e) => {
    const file = e.target.files[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) {
      return;
    }
    const derivedName = file.name.replace(/\.[^./]+$/, "") || file.name;
    this.setState({ pendingFile: file, uploadName: derivedName });
  };

  cancelUpload = () => {
    this.setState({ pendingFile: null, uploadName: "" });
  };

  confirmUpload = () => {
    const { pendingFile, uploadName } = this.state;
    if (!pendingFile || !uploadName.trim()) {
      return;
    }
    this.setState({ uploading: true });
    Uploads.upload(this.props.dataSourceId, pendingFile, uploadName.trim())
      .then((uploaded) => {
        notification.success(`${uploaded.filename} uploaded. Query it as table "${uploaded.view_name}".`);
        this.setState({ pendingFile: null, uploadName: "" });
        this.loadFiles();
      })
      .catch((error) => {
        notification.error(get(error, "response.data.message", "Upload failed."));
      })
      .finally(() => this.setState({ uploading: false }));
  };

  handleDelete = (upload) => {
    Uploads.delete(this.props.dataSourceId, upload.id)
      .then(() => {
        notification.success(`${upload.filename} deleted.`);
        this.loadFiles();
      })
      .catch(() => notification.error("Failed to delete file."));
  };

  render() {
    const { files, loading, uploading, pendingFile, uploadName } = this.state;
    return (
      <div className="m-t-15" data-test="UploadedFilesPanel">
        <h4>Uploaded Files</h4>
        <input
          ref={this.fileInputRef}
          type="file"
          accept=".csv,.parquet"
          style={{ display: "none" }}
          onChange={this.handleFileSelected}
          data-test="UploadedFilesFileInput"
        />
        <Button onClick={() => this.fileInputRef.current.click()}>
          <i className="fa fa-upload m-r-5" aria-hidden="true" />
          Upload File
        </Button>
        <Modal
          title="Name this table"
          visible={!!pendingFile}
          onOk={this.confirmUpload}
          onCancel={this.cancelUpload}
          okText="Upload"
          okButtonProps={{ loading: uploading, disabled: !uploadName.trim() }}
          data-test="UploadNameModal">
          <label htmlFor="uploadedFileName">Name</label>
          <Input
            id="uploadedFileName"
            className="m-t-5"
            value={uploadName}
            onChange={(e) => this.setState({ uploadName: e.target.value })}
            onPressEnter={this.confirmUpload}
            autoFocus
            data-test="UploadNameInput"
          />
          {pendingFile && (
            <p className="text-muted m-t-10">
              <i className="fa fa-file-o m-r-5" aria-hidden="true" />
              {pendingFile.name}
            </p>
          )}
        </Modal>
        <List
          className="m-t-10"
          size="small"
          loading={loading}
          bordered
          dataSource={files}
          locale={{ emptyText: "No files uploaded yet." }}
          renderItem={(file) => (
            <List.Item
              actions={[
                <Popconfirm
                  key="delete"
                  title="Delete this file?"
                  onConfirm={() => this.handleDelete(file)}
                  okText="Delete"
                  okType="danger">
                  <Button type="link" danger>
                    Delete
                  </Button>
                </Popconfirm>,
              ]}>
              <List.Item.Meta
                title={file.display_name || file.filename}
                description={`Table name: ${file.view_name} · ${formatSize(file.size)}`}
              />
            </List.Item>
          )}
        />
      </div>
    );
  }
}

export default UploadedFilesPanel;
