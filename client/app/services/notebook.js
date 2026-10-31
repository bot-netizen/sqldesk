import { axios } from "@/services/axios";

/*
  The notebook API, as the pages use it.

  Thin on purpose. Everything that decides what a cell may do -- whether it can
  run, what it reads, whether it is stale -- is worked out on the server and
  arrives on the cell, because those rules need the install's settings, the
  data source and the other cells' state. Re-deriving any of it here would be
  a second copy that drifts from the first.
*/
const Notebook = {
  all: (params = {}) => axios.get("api/notebooks", { params }),
  get: (id) => axios.get(`api/notebooks/${id}`),
  create: (data = {}) => axios.post("api/notebooks", data),
  save: (id, data) => axios.post(`api/notebooks/${id}`, data),
  archive: (id) => axios.delete(`api/notebooks/${id}`),

  addCell: (notebookId, data = {}) => axios.post(`api/notebooks/${notebookId}/cells`, data),
  saveCell: (notebookId, cellId, data) => axios.post(`api/notebooks/${notebookId}/cells/${cellId}`, data),
  deleteCell: (notebookId, cellId) => axios.delete(`api/notebooks/${notebookId}/cells/${cellId}`),

  // The slice a cell produced, for the page to draw. Per cell rather than
  // inlined into the notebook: a notebook of twenty cells would otherwise be
  // megabytes of JSON before anybody looked at anything.
  cellResult: (notebookId, cellId) => axios.get(`api/notebooks/${notebookId}/cells/${cellId}/result`),

  // Returns a job, in the same shape the query editor already polls.
  runCell: (notebookId, cellId) => axios.post(`api/notebooks/${notebookId}/cells/${cellId}/run`, {}),
  // Cancels the cell that is running. The session and its variables stay.
  // A link for somebody without an account. Nothing is re-run for them --
  // a notebook has no live queries -- so they see the stored slices exactly
  // as the last run left them.
  share: (notebookId) => axios.post(`api/notebooks/${notebookId}/share`, {}),
  unshare: (notebookId) => axios.delete(`api/notebooks/${notebookId}/share`),

  // A cron expression, or "" to take it away. Validated on the server,
  // because a typo that does not parse would otherwise quietly mean "never".
  setSchedule: (notebookId, schedule) => axios.post(`api/notebooks/${notebookId}`, { schedule }),

  // The whole handoff, not the thousand rows on the page. A link rather
  // than an axios call: the browser's own download does the right thing with
  // Content-Disposition, where a fetch would pull the lot into memory first.
  downloadUrl: (notebookId, cellId) => `api/notebooks/${notebookId}/cells/${cellId}/download`,

  // Every cell, in order, as one job on a worker -- not a loop in the
  // browser, which would stop halfway through the moment somebody closed the
  // tab and leave a notebook that looks like it ran.
  runAll: (notebookId) => axios.post(`api/notebooks/${notebookId}/run`, {}),

  stop: (notebookId) => axios.post(`api/notebooks/${notebookId}/stop`, {}),
  // Lets the interpreter go. Variables go with it; the handoffs do not, so the
  // notebook still reads and still re-runs.
  detach: (notebookId) => axios.delete(`api/notebooks/${notebookId}/session`),
};

export default Notebook;
