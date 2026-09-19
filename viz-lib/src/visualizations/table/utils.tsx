import { isNil, map, get, filter, each, sortBy, some, findIndex, toString } from "lodash";
import React from "react";
import cx from "classnames";
import Tooltip from "antd/lib/tooltip";
import ColumnTypes from "../shared/columns";
import { cellStyle, dataBarWidth, changeBetween, normalizeCellFormat, isFormatted, ColumnStats } from "./cellFormat";

export interface CellContext {
  /** Min and max per column, over every row -- not just the visible page. */
  stats: Record<string, ColumnStats | null>;
  /** Each row's values at the previous refresh, by row identity. */
  previous: Map<string, any> | null;
  rowKey: (record: any, index: number) => string;
}

function nextOrderByDirection(direction: any) {
  switch (direction) {
    case "ascend":
      return "descend";
    case "descend":
      return null;
    default:
      return "ascend";
  }
}

function toggleOrderBy(columnName: any, orderBy = [], multiColumnSort = false) {
  // @ts-expect-error ts-migrate(2339) FIXME: Property 'name' does not exist on type 'never'.
  const index = findIndex(orderBy, (i) => i.name === columnName);
  const item = { name: columnName, direction: "ascend" };
  if (index >= 0) {
    // @ts-expect-error ts-migrate(2322) FIXME: Type 'string | null' is not assignable to type 'st... Remove this comment to see the full error message
    item.direction = nextOrderByDirection(orderBy[index].direction);
  }

  if (multiColumnSort) {
    if (!item.direction) {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'name' does not exist on type 'never'.
      return filter(orderBy, (i) => i.name !== columnName);
    }
    if (index >= 0) {
      // @ts-expect-error ts-migrate(2322) FIXME: Type '{ name: any; direction: string; }' is not as... Remove this comment to see the full error message
      orderBy[index] = item;
    } else {
      // @ts-expect-error ts-migrate(2345) FIXME: Argument of type '{ name: any; direction: string; ... Remove this comment to see the full error message
      orderBy.push(item);
    }
    return [...orderBy];
  }
  return item.direction ? [item] : [];
}

function getOrderByInfo(orderBy: any) {
  const result = {};
  each(orderBy, ({ name, direction }, index) => {
    // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
    result[name] = { direction, index: index + 1 };
  });
  return result;
}

export function prepareColumns(
  columns: any,
  searchInput: any,
  orderBy: any,
  onOrderByChange: any,
  cellContext: CellContext | null = null
) {
  columns = filter(columns, "visible");
  columns = sortBy(columns, "order");

  const isMultiColumnSort = orderBy.length > 1;
  const orderByInfo = getOrderByInfo(orderBy);

  let tableColumns = map(columns, (column) => {
    // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
    const isAscend = orderByInfo[column.name] && orderByInfo[column.name].direction === "ascend";
    // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
    const isDescend = orderByInfo[column.name] && orderByInfo[column.name].direction === "descend";

    // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
    const sortColumnIndex = isMultiColumnSort && orderByInfo[column.name] ? orderByInfo[column.name].index : null;

    const result = {
      key: column.name,
      dataIndex: `record[${JSON.stringify(column.name)}]`,
      align: column.alignContent,
      sorter: { multiple: 1 }, // using { multiple: 1 } to allow built-in multi-column sort arrows
      sortOrder: get(orderByInfo, [column.name, "direction"], null),
      title: (
        <React.Fragment>
          {column.description && (
            <span style={{ paddingRight: 5 }}>
              <Tooltip placement="top" title={column.description}>
                <div className="table-visualization-heading">
                  <i className="fa fa-info-circle" aria-hidden="true"></i>
                </div>
              </Tooltip>
            </span>
          )}
          <Tooltip placement="top" title={column.title}>
            <div className="table-visualization-heading" data-sort-column-index={sortColumnIndex}>
              {column.title}
            </div>
          </Tooltip>
        </React.Fragment>
      ),
      onHeaderCell: () => ({
        className: cx({
          "table-visualization-column-is-sorted": isAscend || isDescend,
        }),
        onClick: (event: any) => onOrderByChange(toggleOrderBy(column.name, orderBy, event.shiftKey)),
      }),
    };

    // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
    const initColumn = ColumnTypes[column.displayAs];
    const Component = initColumn(column);
    const format = normalizeCellFormat(column.cellFormat);
    const formatted = cellContext !== null && isFormatted(format);
    // @ts-expect-error ts-migrate(2339) FIXME: Property 'render' does not exist on type '{ key: a... Remove this comment to see the full error message
    result.render = (unused: any, row: any) => {
      const plain = <Component row={row.record} />;
      if (!formatted) {
        return { children: plain, props: { className: `display-as-${column.displayAs}` } };
      }
      const ctx = cellContext as CellContext;
      const value = row.record[column.name];
      const stats = ctx.stats[column.name] || null;
      let children = plain;

      // The change highlight is applied first so that the data bar, when
      // there is one, stays the outermost element. The bar is a block that
      // measures itself against the cell; the highlight is an inline-block
      // that shrinks to its contents, so wrapping the bar in it made the bar
      // measure the number instead -- a sliver behind the digits rather than
      // a bar across the cell, and only ever after the first refresh.
      let change = null;
      if (format.showChange && ctx.previous) {
        const before = ctx.previous.get(ctx.rowKey(row.record, row.index));
        change = changeBetween(before === undefined ? undefined : before[column.name], value);
        if (change) {
          children = (
            // Keyed by the value, so a cell that changes again is a new
            // element and its highlight plays again.
            <span key={String(value)} className={cx("table-cell-changed", `table-cell-changed-${change}`)}>
              {children}
              {change !== "changed" && (
                <span className="table-cell-change-arrow" aria-label={change === "up" ? "went up" : "went down"}>
                  {change === "up" ? " ▲" : " ▼"}
                </span>
              )}
            </span>
          );
        }
      }

      if (format.dataBar) {
        const width = dataBarWidth(value, stats);
        if (width !== null) {
          children = (
            <span className="table-cell-databar">
              <i style={{ width: `${width}%` }} aria-hidden="true" />
              <span>{children}</span>
            </span>
          );
        }
      }

      return {
        children,
        props: {
          className: `display-as-${column.displayAs}`,
          style: cellStyle(value, format, stats),
        },
      };
    };

    return result;
  });

  tableColumns.push({
    key: "###SQLDesk::Visualizations::Table::Spacer###",
    // @ts-expect-error ts-migrate(2322) FIXME: Type 'null' is not assignable to type 'string'.
    dataIndex: null,
    // @ts-expect-error ts-migrate(2322) FIXME: Type 'string' is not assignable to type 'Element'.
    title: "",
    className: "table-visualization-spacer",
    render: () => "",
    // @ts-expect-error ts-migrate(2741) FIXME: Property 'onClick' is missing in type '{ className... Remove this comment to see the full error message
    onHeaderCell: () => ({ className: "table-visualization-spacer" }),
  });

  if (searchInput) {
    // Add searchInput as the ColumnGroup for all table columns
    tableColumns = [
      {
        key: "table-search",
        title: searchInput,
        // @ts-expect-error ts-migrate(2741) FIXME: Property 'onClick' is missing in type '{ className... Remove this comment to see the full error message
        onHeaderCell: () => ({ className: "table-visualization-search" }),
        children: tableColumns,
      },
    ];
  }

  return tableColumns;
}

export function initRows(rows: any) {
  // `index` is the row's place in the result, which survives sorting and
  // searching -- what matches a row to itself across refreshes when nothing
  // better identifies it.
  return map(rows, (record, index) => ({ key: `record${index}`, record, index }));
}

export function filterRows(rows: any, searchTerm: any, searchColumns: any) {
  if (searchTerm !== "" && searchColumns.length > 0) {
    searchTerm = searchTerm.toUpperCase();
    const matchFields = map(searchColumns, (column) => {
      // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
      const initColumn = ColumnTypes[column.displayAs];
      const { prepareData } = initColumn(column);
      return (row: any) => {
        const { text } = prepareData(row);
        return toString(text).toUpperCase().indexOf(searchTerm) >= 0;
      };
    });

    return filter(rows, (row) => some(matchFields, (match) => match(row.record)));
  }
  return rows;
}

export function sortRows(rows: any, orderBy: any) {
  if (orderBy.length === 0 || rows.length === 0) {
    return rows;
  }

  const directions = { ascend: 1, descend: -1 };

  // Create a copy of array before sorting, because .sort() will modify original array
  return [...rows].sort((a, b) => {
    let va;
    let vb;
    for (let i = 0; i < orderBy.length; i += 1) {
      va = a.record[orderBy[i].name];
      vb = b.record[orderBy[i].name];
      if (isNil(va) || va < vb) {
        // if a < b - we should return -1, but take in account direction
        // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
        return -1 * directions[orderBy[i].direction];
      }
      if (va > vb || isNil(vb)) {
        // if a > b - we should return 1, but take in account direction
        // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
        return 1 * directions[orderBy[i].direction];
      }
    }
    return 0;
  });
}
