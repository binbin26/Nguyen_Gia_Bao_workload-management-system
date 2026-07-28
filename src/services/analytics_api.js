import { authHttp } from "./auth_api";

// This exact constant is shared by useQuery and every invalidation site.
export const OVERLOAD_ALERTS_QUERY_KEY = Object.freeze([
  "analytics",
  "overloads",
]);
export const STAFF_KPI_QUERY_KEY = Object.freeze(["analytics", "staff-kpi"]);

function unwrapOverloads(payload) {
  const data = payload?.data;

  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  if (Array.isArray(data?.overloads)) {
    return data.overloads;
  }

  if (Array.isArray(payload?.items)) {
    return payload.items;
  }

  return [];
}

export async function getOverloadAlerts() {
  const response = await authHttp.get("/api/v1/analytics/overloads");
  return unwrapOverloads(response.data);
}

export async function getStaffKpis() {
  const response = await authHttp.get("/api/v1/analytics/staff-kpi");
  const data = response.data?.data;

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  return Array.isArray(data) ? data : [];
}

export async function resolveOverloadAlert(logId, selectedStaffId) {
  const response = await authHttp.post(
    `/api/v1/analytics/overloads/${logId}/resolve`,
    {
      action_taken: "Approved_Suggestion",
      selected_staff_id: selectedStaffId,
    },
  );

  return response.data?.data || response.data;
}

export async function applyCapacitySuggestion(staffId, selectedStaffId) {
  const response = await authHttp.post(
    `/api/v1/analytics/overloads/capacity/${encodeURIComponent(staffId)}/apply`,
    {
      selected_staff_id: selectedStaffId,
    },
  );

  return response.data?.data || response.data;
}
