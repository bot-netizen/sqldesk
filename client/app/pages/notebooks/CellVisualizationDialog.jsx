import React, { useMemo, useState } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Select from "antd/lib/select";
import Input from "antd/lib/input";
import { filter, map, pick, sortBy } from "lodash";

import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import { useUniqueId } from "@/lib/hooks/useUniqueId";
import { registeredVisualizations, getDefaultVisualization } from "@sqldesk/viz/lib";
import { Editor, Renderer } from "@/components/visualizations/visualizationComponents";

import "@/components/visualizations/EditVisualizationDialog.less";

/*
  A chart on a cell's output.

  The same editor and the same renderer the query editor uses -- these are the
  per-type `Editor` components out of viz-lib, so every chart type SQLDesk has
  is here, configured the same way, with no notebook-shaped copy of any of it.

  What is different is where it is kept. A `Visualization` row belongs to a
  query: dashboards enumerate them, the API serves them, widgets point at them.
  A cell is not a query, and giving the table a nullable second parent would
  put a notebook into every one of those paths for a feature that is only
  meant to draw a chart on a page. So a cell's chart lives in the cell's own
  `options`, which is a column it already has.

  The cost is stated rather than hidden: a cell's chart cannot become a
  dashboard widget. That was deferred to 0.9 anyway, for a different and
  better reason -- refreshing a widget backed by cell seven means running
  cells one to seven on an interpreter, on a dashboard's refresh interval,
  which is a scheduling design rather than a widget.
*/
function CellVisualizationDialog({ dialog, cell, data }) {
  const saved = (cell.options || {}).visualization || null;
  const isNew = !saved;

  const defaults = useMemo(() => {
    const config = saved ? registeredVisualizations[saved.type] : getDefaultVisualization();
    return {
      type: config.type,
      name: saved ? saved.name : config.name,
      options: config.getOptions(saved ? saved.options : {}, data),
    };
  }, [saved, data]);

  const [type, setType] = useState(defaults.type);
  const [name, setName] = useState(defaults.name);
  const [options, setOptions] = useState(defaults.options);

  function onTypeChanged(newType) {
    const config = registeredVisualizations[newType];
    setType(newType);
    setName(config.name);
    setOptions(config.getOptions({}, data));
  }

  function onOptionsChanged(newOptions) {
    setOptions(registeredVisualizations[type].getOptions(newOptions, data));
  }

  // Changing the type of an existing chart would silently throw away the
  // options somebody configured, so the chooser offers every type when the
  // chart is new and only the current one afterwards -- exactly as the query
  // editor's dialog does.
  const available = isNew
    ? filter(sortBy(registeredVisualizations, ["name"]), (one) => !one.isDeprecated)
    : pick(registeredVisualizations, [type]);

  const typeId = useUniqueId("cell-visualization-type");
  const nameId = useUniqueId("cell-visualization-name");

  return (
    <Modal
      {...dialog.props}
      wrapClassName="ant-modal-fullscreen"
      title={`Chart for ${cell.name}`}
      okText="Save"
      onOk={() => dialog.close({ type, name, options })}
      onCancel={dialog.dismiss}
      wrapProps={{ "data-test": "CellVisualizationDialog" }}
    >
      <div className="edit-visualization-dialog">
        <div className="visualization-settings">
          <div className="m-b-15">
            <label htmlFor={typeId}>Visualization Type</label>
            <Select
              data-test="CellVisualizationType"
              id={typeId}
              className="w-100"
              disabled={!isNew}
              virtual={false}
              value={type}
              onChange={onTypeChanged}
            >
              {map(available, (one) => (
                <Select.Option key={one.type}>{one.name}</Select.Option>
              ))}
            </Select>
          </div>
          <div className="m-b-15">
            <label htmlFor={nameId}>Name</label>
            <Input
              data-test="CellVisualizationName"
              id={nameId}
              className="w-100"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div data-test="CellVisualizationEditor">
            <Editor
              type={type}
              data={data}
              options={options}
              visualizationName={name}
              onOptionsChange={onOptionsChanged}
            />
          </div>
        </div>
        <div className="visualization-preview">
          <div className="scrollbox" data-test="CellVisualizationPreview">
            <Renderer type={type} data={data} options={options} visualizationName={name} />
          </div>
        </div>
      </div>
    </Modal>
  );
}

CellVisualizationDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  cell: PropTypes.object.isRequired,
  data: PropTypes.object.isRequired,
};

export default wrapDialog(CellVisualizationDialog);
