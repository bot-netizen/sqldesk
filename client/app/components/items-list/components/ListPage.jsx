import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import { difference, filter, includes, isFunction, map } from "lodash";
import Link from "@/components/Link";
import PlainButton from "@/components/PlainButton";
import getTags from "@/services/getTags";

import "./ListPage.less";

/*
  Shared shell for list pages: page header, horizontal view tabs and tag
  chips.

  Purpose-built rather than reusing items-list/Sidebar: those render antd's
  Menu in mode="inline", which is vertical by construction. Bending it
  sideways would fight the component.

  Filters live above the table rather than in a left rail because these
  tables have grown wide enough that ~250px of vertical rail was the single
  biggest constraint on the list itself.
*/

export function Shell({ children, className }) {
  return <div className={cx("list-page-shell", className)}>{children}</div>;
}

Shell.propTypes = { children: PropTypes.node, className: PropTypes.string };
Shell.defaultProps = { children: null, className: null };

export function Header({ title, subtitle, children }) {
  return (
    <header className="list-page-header">
      <div className="list-page-heading">
        <h1>{title}</h1>
        {subtitle && <p className="list-page-subtitle">{subtitle}</p>}
      </div>
      <div className="list-page-header-actions">{children}</div>
    </header>
  );
}

Header.propTypes = {
  title: PropTypes.node,
  subtitle: PropTypes.node,
  children: PropTypes.node,
};

Header.defaultProps = { title: null, subtitle: null, children: null };

export function ViewTabs({ items, selected, ariaLabel }) {
  const available = filter(items, (item) => (isFunction(item.isAvailable) ? item.isAvailable() : true));
  if (available.length === 0) {
    return null;
  }

  return (
    <nav className="list-page-tabs" aria-label={ariaLabel}>
      {map(available, (item) => (
        <Link
          key={item.key}
          href={item.href}
          className={cx("list-page-tab", { "list-page-tab-active": item.key === selected })}
          aria-current={item.key === selected ? "page" : undefined}
        >
          {item.title}
        </Link>
      ))}
    </nav>
  );
}

ViewTabs.propTypes = {
  items: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      href: PropTypes.string.isRequired,
      title: PropTypes.string.isRequired,
      isAvailable: PropTypes.func,
    })
  ),
  selected: PropTypes.string,
  ariaLabel: PropTypes.string,
};

ViewTabs.defaultProps = { items: [], selected: null, ariaLabel: "Views" };

export function TagChips({ tagsUrl, onChange, aside }) {
  const [allTags, setAllTags] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);

  useEffect(() => {
    let cancelled = false;
    getTags(tagsUrl).then((tags) => {
      if (!cancelled) {
        setAllTags(tags);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [tagsUrl]);

  // Shift-click accumulates, matching the sidebar TagsList this replaces, so
  // the interaction does not change just because the chips moved.
  const toggleTag = useCallback(
    (event, tag) => {
      let next;
      if (event.shiftKey) {
        next = includes(selectedTags, tag) ? difference(selectedTags, [tag]) : [...selectedTags, tag];
      } else {
        next = includes(selectedTags, tag) && selectedTags.length === 1 ? [] : [tag];
      }
      setSelectedTags(next);
      if (onChange) {
        onChange([...next]);
      }
    },
    [selectedTags, onChange]
  );

  // Still render the row when there are no tags: it carries the sort
  // indicator, which is not about tags.
  if (allTags.length === 0 && !aside) {
    return null;
  }

  return (
    <div className="list-page-tags-row">
      <div className="list-page-tags" role="group" aria-label="Filter by tag">
        {map(allTags, (tag) => {
          const isSelected = includes(selectedTags, tag.name);
          return (
            <PlainButton
              key={tag.name}
              className={cx("list-page-tag", { "list-page-tag-selected": isSelected })}
              aria-pressed={isSelected}
              onClick={(event) => toggleTag(event, tag.name)}
            >
              {tag.name}
              {tag.count > 0 && <span className="list-page-tag-count">{tag.count}</span>}
              {isSelected && (
                <span className="list-page-tag-clear" aria-hidden="true">
                  ×
                </span>
              )}
            </PlainButton>
          );
        })}
      </div>
      {aside && <div className="list-page-tags-aside">{aside}</div>}
    </div>
  );
}

TagChips.propTypes = {
  tagsUrl: PropTypes.string.isRequired,
  onChange: PropTypes.func,
  aside: PropTypes.node,
};

TagChips.defaultProps = { onChange: null, aside: null };
