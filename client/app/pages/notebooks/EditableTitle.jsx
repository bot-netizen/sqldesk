import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";

/*
  A name you change by clicking it.

  Shared by the notebook's own name and each cell's title, because they are
  the same interaction and were about to be written twice. Edited in place
  rather than behind a dialog: a title nobody can be bothered to set leaves a
  contents list reading `cell_1 … cell_30`, and a dialog is enough friction to
  cause exactly that.

  Enter commits, Escape abandons, blur commits -- the three a person tries
  without being told. Whitespace is trimmed and an empty result means "no
  title", not a title that happens to be blank.
*/
export default function EditableTitle({ value, placeholder, canEdit, onChange, className, inputClassName, dataTest }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");

  useEffect(() => setDraft(value || ""), [value]);

  const commit = useCallback(() => {
    setEditing(false);
    const wanted = draft.trim();
    if (wanted !== (value || "")) {
      onChange(wanted);
    }
  }, [draft, value, onChange]);

  if (!canEdit) {
    return value ? (
      <span className={className} data-test={dataTest}>
        {value}
      </span>
    ) : null;
  }

  if (editing) {
    return (
      <input
        className={inputClassName}
        value={draft}
        autoFocus
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            commit();
          }
          if (e.key === "Escape") {
            setDraft(value || "");
            setEditing(false);
          }
        }}
        data-test={`${dataTest}Input`}
      />
    );
  }

  return (
    <span
      className={cx(className, { "notebook-title-unset": !value })}
      onClick={() => setEditing(true)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && setEditing(true)}
      data-test={dataTest}
    >
      {value || placeholder}
    </span>
  );
}

EditableTitle.propTypes = {
  value: PropTypes.string,
  placeholder: PropTypes.string,
  canEdit: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
  className: PropTypes.string,
  inputClassName: PropTypes.string,
  dataTest: PropTypes.string,
};

EditableTitle.defaultProps = {
  value: null,
  placeholder: "Name this",
  canEdit: false,
  className: null,
  inputClassName: null,
  dataTest: "EditableTitle",
};
