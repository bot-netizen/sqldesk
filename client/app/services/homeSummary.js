import { axios } from "@/services/axios";

/**
 * What the home page shows: counts of the things the current user made, and
 * their slowest scheduled queries.
 *
 * Distinct from organizationStatus, which counts the whole organization and
 * drives the onboarding steps.
 */
export function getHomeSummary() {
  return axios.get("api/home/summary");
}

export default { getHomeSummary };
