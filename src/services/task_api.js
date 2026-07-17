import { authHttp } from "./auth_api";

function unwrapTasks(payload) {
  const data = payload?.data;

  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.tasks)) {
    return data.tasks;
  }

  if (Array.isArray(payload?.tasks)) {
    return payload.tasks;
  }

  return [];
}

export async function getTasks() {
  const response = await authHttp.get("/api/v1/tasks");
  return unwrapTasks(response.data);
}

export async function nextStepTask(taskId) {
  const response = await authHttp.post(`/api/v1/tasks/${taskId}/next-step`);
  return response.data?.data || response.data;
}
