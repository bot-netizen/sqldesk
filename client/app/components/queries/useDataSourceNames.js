import { useEffect, useState } from "react";
import { keyBy, mapValues } from "lodash";
import DataSource from "@/services/data-source";

/*
  Maps data source id -> name, so a list view can show which source a query
  runs against. The query list endpoint serves data_source_id but not the
  name, and widening it would mean a join per list request.

  Fetched per mount rather than memoised at module scope: the endpoint is
  small, and a cached name would go stale as soon as anyone renames a source.
  If this ever shows up in profiling it is safe to cache, provided the data
  source settings pages invalidate it on save and delete.
*/
export default function useDataSourceNames() {
  const [names, setNames] = useState({});

  useEffect(() => {
    let cancelled = false;
    DataSource.query()
      .then((sources) => {
        if (!cancelled) {
          setNames(mapValues(keyBy(sources, "id"), "name"));
        }
      })
      // A name we cannot resolve renders as a dash; it is not worth an error
      // state on a secondary column.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return names;
}
