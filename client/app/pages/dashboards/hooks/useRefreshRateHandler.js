import { isNaN, max, min } from "lodash";
import { useEffect, useState, useMemo } from "react";
import location from "@/services/location";
import { policy } from "@/services/policy";
import useImmutableCallback from "@/lib/hooks/useImmutableCallback";

// An ordinary dashboard's auto-refresh is a timer in every open tab, so it
// never runs faster than every ten minutes -- an old "?refresh=60" link is
// raised to that. Anything faster is what live dashboards are for.
export const MINIMUM_REFRESH_RATE = 600;

export function getLimitedRefreshRate(refreshRate) {
  const allowedIntervals = policy.getDashboardRefreshIntervals();
  return max([MINIMUM_REFRESH_RATE, min(allowedIntervals), refreshRate]);
}

function getRefreshRateFromUrl() {
  const refreshRate = parseFloat(location.search.refresh);
  return isNaN(refreshRate) ? null : getLimitedRefreshRate(refreshRate);
}

export default function useRefreshRateHandler(refreshDashboard) {
  const [refreshRate, setRefreshRate] = useState(getRefreshRateFromUrl());

  // `refreshDashboard` may change quite frequently (on every update of `dashboard` instance), but we
  // have to keep the same timer running, because timer will restart when re-creating, and instead of
  // running refresh every N seconds - it will run refresh every N seconds after last dashboard update
  // (which is not right obviously)
  const doRefreshDashboard = useImmutableCallback(refreshDashboard);

  // URL and timer should be updated only when `refreshRate` changes
  useEffect(() => {
    location.setSearch({ refresh: refreshRate || null }, true);
    if (refreshRate) {
      // The rate goes along so the refresh can accept any result younger than
      // it -- one tab's refresh then serves every other tab's.
      const refreshTimer = setInterval(() => doRefreshDashboard(refreshRate), refreshRate * 1000);
      return () => clearInterval(refreshTimer);
    }
  }, [refreshRate, doRefreshDashboard]);

  return useMemo(
    () => [refreshRate, (rate) => setRefreshRate(getLimitedRefreshRate(rate)), () => setRefreshRate(null)],
    [refreshRate]
  );
}
