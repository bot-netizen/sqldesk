"""
What SQLDesk knows about a warehouse, without a model.

`catalog` harvests what exists and what is used, and serves it to MCP;
`optimizer` parses SQL and reports expensive shapes. Neither calls out to
anything: the model is the MCP client's, on the other end of the connection.
"""
