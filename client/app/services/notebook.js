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
  stop: (notebookId) => axios.post(`api/notebooks/${notebookId}/stop`, {}),
  // Lets the interpreter go. Variables go with it; the handoffs do not, so the
  // notebook still reads and still re-runs.
  detach: (notebookId) => axios.delete(`api/notebooks/${notebookId}/session`),
};

export default Notebook;
