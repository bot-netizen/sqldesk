import { useReducer, useEffect, useRef } from "react";
import location from "@/services/location";
import recordEvent from "@/services/recordEvent";
import { ExecutionStatus } from "@/services/query-result";
import notifications from "@/services/notifications";
import useImmutableCallback from "@/lib/hooks/useImmutableCallback";
import { newestStored, noOlderThan, runNow } from "@/services/freshness";

/*
  What the query page opens on: the newest stored result, so opening a query
  shows what it last returned without running it again. `?maxAge=N` in the URL
  overrides that -- a link that wants a result no older than N seconds, and
  will run the query if there is none.
*/
function freshnessOnOpen() {
  const { maxAge } = location.search;
  return maxAge !== undefined ? noOlderThan(Number(maxAge)) : newestStored();
}

const reducer = (prevState, updatedProperty) => ({
  ...prevState,
  ...updatedProperty,
});

// This is currently specific to a Query page, we can refactor
// it slightly to make it suitable for dashboard widgets instead of the other solution it
// has in there.
export default function useQueryExecute(query) {
  const [executionState, setExecutionState] = useReducer(reducer, {
    queryResult: null,
    isExecuting: false,
    loadedInitialResults: false,
    executionStatus: null,
    isCancelling: false,
    cancelCallback: null,
    error: null,
  });

  const queryResultInExecution = useRef(null);
  // When the page goes, stop asking after its query: nothing is waiting for
  // the answer. Clearing the ref also stops the late answer setting state.
  useEffect(() => {
    return () => {
      const running = queryResultInExecution.current;
      if (running && running.abandon) {
        running.abandon();
      }
      queryResultInExecution.current = null;
    };
  }, []);

  // `quiet`: a repeat nobody asked for by hand -- the stream editor's refresh
  // -- records no event and raises no notification.
  const executeQuery = useImmutableCallback((request = runNow(), queryExecutor, { quiet = false } = {}) => {
    let newQueryResult;
    if (queryExecutor) {
      newQueryResult = queryExecutor();
    } else {
      newQueryResult = query.getQueryResult(request);
    }

    if (!quiet) {
      recordEvent("execute", "query", query.id);
      notifications.getPermissions();
    }

    // A new run replaces the old: nothing will read the old one's answer.
    const replaced = queryResultInExecution.current;
    if (replaced && replaced !== newQueryResult && replaced.abandon) {
      replaced.abandon();
    }
    queryResultInExecution.current = newQueryResult;

    setExecutionState({
      updatedAt: newQueryResult.getUpdatedAt(),
      executionStatus: newQueryResult.getStatus(),
      isExecuting: true,
      cancelCallback: () => {
        recordEvent("cancel_execute", "query", query.id);
        setExecutionState({ isCancelling: true });
        newQueryResult.cancelExecution();
      },
    });

    const onStatusChange = (status) => {
      if (queryResultInExecution.current === newQueryResult) {
        setExecutionState({ updatedAt: newQueryResult.getUpdatedAt(), executionStatus: status });
      }
    };

    newQueryResult
      .toPromise(onStatusChange)
      .then((queryResult) => {
        if (queryResultInExecution.current === newQueryResult) {
          // TODO: this should probably belong in the QueryEditor page.
          if (queryResult && queryResult.query_result.query === query.query) {
            query.latest_query_data_id = queryResult.getId();
            query.queryResult = queryResult;
          }

          if (executionState.loadedInitialResults && !quiet) {
            notifications.showNotification("SQLDesk", `${query.name} updated.`);
          }

          setExecutionState({
            queryResult,
            loadedInitialResults: true,
            error: null,
            isExecuting: false,
            isCancelling: false,
            executionStatus: null,
          });
        }
      })
      .catch((queryResult) => {
        if (queryResultInExecution.current === newQueryResult) {
          if (executionState.loadedInitialResults && !quiet) {
            notifications.showNotification("SQLDesk", `${query.name} failed to run: ${queryResult.getError()}`);
          }

          setExecutionState({
            queryResult,
            loadedInitialResults: true,
            error: queryResult.getError(),
            isExecuting: false,
            isCancelling: false,
            executionStatus: ExecutionStatus.FAILED,
          });
        }
      });
  });

  const queryRef = useRef(query);
  queryRef.current = query;

  useEffect(() => {
    // TODO: this belongs on the query page?
    // loadedInitialResults can be removed if so
    if (queryRef.current.hasResult() || queryRef.current.paramsRequired()) {
      executeQuery(freshnessOnOpen());
    } else {
      setExecutionState({ loadedInitialResults: true });
    }
  }, [executeQuery]);

  return { ...executionState, ...{ executeQuery } };
}
