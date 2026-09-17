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
    // A click anywhere in a Dropdown's overlay closes it, which for a panel
    // built around a text field means the field vanishes the moment you try to
    // type in it. Only clicks outside should close this one.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events
    <div className="list-page-filter-panel" onClick={(event) => event.stopPropagation()}>
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

/*
  Whether a column is the user's to hide.

  One definition, used by both the menu and the filtering, so the only columns
  that can be hidden are the ones the menu offers to bring back. A column with
  no title is structural -- the favourites star, the row actions -- and hiding
  it would take away the menu itself with nothing left to restore it.
*/
function isToggleable(column) {
  return typeof column.title === "string" && column.title !== "";
}

/*
  The columns a list should actually render.

  Exported as a pair with ColumnsControl so the two readings of "columns" stay
  apart: the control is given every column the list can show, and the table is
  given this. Doing the filtering inline at the call site is how a hidden
  column came to be missing from the menu that was supposed to bring it back.
*/
export function visibleColumns(columns, hidden) {
  return columns.filter((column) => !isToggleable(column) || !includes(hidden, column.title));
}

export function ColumnsControl({ columns, hidden, onToggle }) {
  // `columns` must be every column the list can show, not the ones it is
  // showing: a hidden column has to stay in this menu or there is no way to
  // bring it back.
  const toggleable = useMemo(() => columns.filter(isToggleable), [columns]);

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
