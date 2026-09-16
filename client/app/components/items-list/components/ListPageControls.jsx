import React, { useCallback, useMemo } from "react";
import PropTypes from "prop-types";
import { includes, map, without } from "lodash";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Checkbox from "antd/lib/checkbox";
import Input from "antd/lib/input";
import FilterOutlinedIcon from "@ant-design/icons/FilterOutlined";
import TableOutlinedIcon from "@ant-design/icons/TableOutlined";
import PlainButton from "@/components/PlainButton";
import localOptions from "@/lib/localOptions";

import "./ListPageControls.less";

/*
  The Filter and Columns controls in a list page header.

  Both do real work rather than sitting there as chrome: Filter holds the
  search field, which is server-side and so filters the whole result set,
  and Columns toggles visibility per column. A control that looked like it
  filtered but only affected the page in front of you would be worse than
  no control at all.
*/

export function FilterControl({ value, onChange, placeholder, label }) {
  const overlay = (
    <div className="list-page-filter-panel">
      <div className="list-page-filter-label">{label}</div>
      <Input
        allowClear
        autoFocus
        placeholder={placeholder}
        value={value}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );

  return (
    <Dropdown overlay={overlay} trigger={["click"]} placement="bottomRight">
      <PlainButton className={`list-page-control${value ? " list-page-control-on" : ""}`} data-test="ListFilterButton">
        <FilterOutlinedIcon aria-hidden="true" />
        <span>Filter</span>
      </PlainButton>
    </Dropdown>
  );
}

FilterControl.propTypes = {
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  placeholder: PropTypes.string,
  label: PropTypes.string,
};

FilterControl.defaultProps = { value: "", placeholder: "Search…", label: "Search" };

/*
  Hidden columns are stored per list (storageKey) rather than globally, so
  hiding Runtime on queries does not hide something unrelated elsewhere.
*/
export function useHiddenColumns(storageKey) {
  const optionKey = `hiddenColumns:${storageKey}`;
  const [hidden, setHidden] = React.useState(() => localOptions.get(optionKey, []) || []);

  const toggle = useCallback(
    (title) => {
      setHidden((current) => {
        const next = includes(current, title) ? without(current, title) : [...current, title];
        localOptions.set(optionKey, next);
        return next;
      });
    },
    [optionKey]
  );

  return [hidden, toggle];
}

export function ColumnsControl({ columns, hidden, onToggle }) {
  // Columns with no title are structural (favourites star, row actions) and
  // are not the user's to hide.
  const toggleable = useMemo(() => columns.filter((c) => typeof c.title === "string" && c.title !== ""), [columns]);

  const overlay = (
    <Menu className="list-page-columns-menu">
      {map(toggleable, (column) => (
        <Menu.Item key={column.title}>
          <Checkbox checked={!includes(hidden, column.title)} onChange={() => onToggle(column.title)}>
            {column.title}
          </Checkbox>
        </Menu.Item>
      ))}
    </Menu>
  );

  return (
    <Dropdown overlay={overlay} trigger={["click"]} placement="bottomRight">
      <PlainButton
        className={`list-page-control${hidden.length ? " list-page-control-on" : ""}`}
        data-test="ListColumnsButton"
      >
        <TableOutlinedIcon aria-hidden="true" />
        <span>Columns</span>
      </PlainButton>
    </Dropdown>
  );
}

ColumnsControl.propTypes = {
  columns: PropTypes.arrayOf(PropTypes.object).isRequired,
  hidden: PropTypes.arrayOf(PropTypes.string).isRequired,
  onToggle: PropTypes.func.isRequired,
};
