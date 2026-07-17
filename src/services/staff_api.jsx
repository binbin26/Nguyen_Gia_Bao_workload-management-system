import { authHttp } from "./auth_api";

function unwrapStaffs(payload) {
  const data = payload?.data;

  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.staffs)) {
    return data.staffs;
  }

  if (Array.isArray(payload?.staffs)) {
    return payload.staffs;
  }

  return [];
}

export async function getStaffs() {
  const response = await authHttp.get("/api/v1/staffs");
  return unwrapStaffs(response.data);
}
