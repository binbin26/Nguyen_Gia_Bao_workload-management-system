import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const authHttp = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export function setAuthToken(token) {
  if (token) {
    authHttp.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete authHttp.defaults.headers.common.Authorization;
  }
}

authHttp.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function loginRequest({ username, password }) {
  const response = await authHttp.post("/api/v1/auth/login", {
    username,
    password,
  });
  return response.data.data;
}
