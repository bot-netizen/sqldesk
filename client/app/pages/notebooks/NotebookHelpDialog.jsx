import React from "react";
import Modal from "antd/lib/modal";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";

/*
  How notebooks work, where somebody is stuck.

  In the page rather than on the docs site: the thing people need to know is
  one sentence long -- a later cell reads an earlier one *by its name* -- and
  sending them to a website to learn it means most of them never do. The
  rules that surprise people are here too, because every one of them is a
  refusal somebody will otherwise meet by pressing Run.
*/
function Rule({ title, children }) {
  return (
    <div className="notebook-help-rule">
      <h4>{title}</h4>
      {children}
    </div>
  );
}

export function NotebookHelpDialog({ dialog }) {
  return (
    <Modal {...dialog.props} title="How notebooks work" width={640} footer={null} data-test="NotebookHelpDialog">
      <div className="notebook-help">
        <p>
          A query ends in one statement. A notebook is a chain: pull this, join it to that, reshape it in Python, look.
          Each step is named, and the next step reads it by that name.
        </p>

        <Rule title="A later cell reads an earlier one by name">
          <p>
            Name a cell <code>orders</code> and the cells below it can use that name — as a table in SQL, as a
            dataframe in Python.
          </p>
          <pre>{`-- a SQL cell named "orders", against your warehouse
select id, city, total from sales where created_at > now() - interval '7 days'`}</pre>
          <pre>{`-- a later SQL cell, with no data source: it reads the cells above
select city, sum(total) as takings from orders group by city order by takings desc`}</pre>
          <pre>{`# a Python cell: orders is already a pandas DataFrame
by_city = orders.groupby("city")["total"].sum().reset_index()
by_city`}</pre>
          <p>
            <strong>You do not have to remember the name.</strong> It is on the cell, in monospace, beside the title —
            click it and it is on your clipboard. The names a cell can read are listed under its editor, and typing in
            a cell completes against them: the cells above, and the columns inside each one.
          </p>
          <p>
            The name is the identifier and the title is for reading. Titling a cell sets the name to match while
            nothing is referring to it yet, so there is usually only one thing to fill in; after that, renaming it is
            in the cell’s ⋯ menu and every reference keeps working.
          </p>
        </Rule>

        <Rule title="A SQL cell either queries a data source or reads earlier cells — never both">
          <p>
            Your warehouse has never heard of a cell called <code>orders</code>, and SQLDesk will not push four million
            rows into it to pretend otherwise. Pick the data source to query it; pick “SQL over earlier cells” to work
            on what is already here.
          </p>
        </Rule>

        <Rule title="A Python cell computes; it cannot query">
          <p>
            It reads an earlier cell’s output and nothing else. That is deliberate: no credential ever reaches the
            interpreter, because there is nothing there for it to reach.
          </p>
          <p>
            End a cell on a dataframe and the next cell can read it. End on a chart and it is drawn —{" "}
            <code>matplotlib</code>, <code>seaborn</code>, <code>df.plot()</code> and <code>plotly</code> all work.
          </p>
          <pre>{`import plotly.express as px
px.bar(by_city, x="city", y="total", title="Takings by city")`}</pre>
        </Rule>

        <Rule title="Stale is shown, never corrected for you">
          <p>
            If a cell you read has re-run since, this cell says so and is left exactly as it was. The number on screen
            is still the number that was computed. Re-running is your decision.
          </p>
        </Rule>

        <Rule title="What you see is a slice; what the next cell reads is all of it">
          <p>
            The table on the page is the first thousand rows. The whole result is handed to the next cell, and{" "}
            <strong>Download</strong> gives you the whole thing too — not the slice.
          </p>
        </Rule>

        <Rule title="Notebooks are in beta">
          <p>
            Which means: use them, they work, and they are supported — and what they do may change between releases
            in ways the rest of SQLDesk will not. Nothing here will lose your work: a notebook is rows in the
            database like a query or a dashboard. What may move is the shape of the page and what a cell is allowed
            to do.
          </p>
        </Rule>

        <Rule title="Running the lot, and running it on a schedule">
          <p>
            <strong>Run all</strong> runs the chain in order and stops at the first cell that fails, because everything
            below it would be reading what that cell did not produce. <strong>Schedule</strong> does the same on a cron
            — publish the notebook first.
          </p>
        </Rule>
      </div>
    </Modal>
  );
}

NotebookHelpDialog.propTypes = { dialog: DialogPropType.isRequired };

export default wrapDialog(NotebookHelpDialog);
