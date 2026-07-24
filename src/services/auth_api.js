import axios from "axios";

// Same-origin by default. In local development Vite proxies /api to FastAPI;
// in production the reverse proxy should expose both under the same site so
// SameSite=Strict cookies continue to work.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const CSRF_ENDPOINT = "/api/v1/auth/csrf";
const UNSAFE_METHODS = new Set(["post", "put", "patch", "delete"]);

export const authHttp = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 15_000,
});

// A separate client prevents the CSRF bootstrap request from recursively
// entering authHttp's request interceptor.
const csrfHttp = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 10_000,
});

let csrfToken = null;
let csrfRequest = null;
let refreshRequest = null;
const SESSION_EXPIRED_EVENT = "auth:session-expired";

export function invalidateCsrfToken() {
  csrfToken = null;
}

async function getCsrfToken({ force = false } = {}) {
  if (force) {
    csrfToken = null;
  }
  if (csrfToken) {
    return csrfToken;
  }
  if (csrfRequest) {
    return csrfRequest;
  }

  csrfRequest = csrfHttp
    .get(CSRF_ENDPOINT)
    .then((response) => {
      const token = response.data?.data?.csrf_token;
      if (!token) {
        throw new Error("CSRF endpoint did not return a token");
      }
      csrfToken = token;
      return token;
    })
    .finally(() => {
      csrfRequest = null;
    });

  return csrfRequest;
}

function setRequestHeader(config, name, value) {
  if (typeof config.headers?.set === "function") {
    config.headers.set(name, value);
    return;
  }
  config.headers = { ...config.headers, [name]: value };
}

authHttp.interceptors.request.use(async (config) => {
  const method = (config.method || "get").toLowerCase();
  if (UNSAFE_METHODS.has(method)) {
    const token = await getCsrfToken();
    setRequestHeader(config, "X-CSRF-Token", token);
  }
  return config;
});

function isAuthBootstrapRequest(url = "") {
  return url.includes("/api/v1/auth/login") || url.includes("/api/v1/auth/refresh");
}

authHttp.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    const method = (originalRequest.method || "get").toLowerCase();
    const errorCode = error.response?.data?.error_code;

    // A token can become stale when login/logout rotates the cookie. Fetch one
    // fresh value and retry the mutation exactly once.
    if (
      error.response?.status === 403 &&
      UNSAFE_METHODS.has(method) &&
      String(errorCode || "").startsWith("CSRF_") &&
      !originalRequest._csrfRetry
    ) {
      originalRequest._csrfRetry = true;
      const token = await getCsrfToken({ force: true });
      setRequestHeader(originalRequest, "X-CSRF-Token", token);
      return authHttp(originalRequest);
    }

    // Access JWTs are intentionally short-lived. A single shared refresh
    // promise prevents concurrent 401 responses from reusing the one-time
    // refresh token and triggering replay protection.
    if (
      error.response?.status === 401 &&
      !originalRequest._authRetry &&
      !isAuthBootstrapRequest(originalRequest.url)
    ) {
      originalRequest._authRetry = true;
      refreshRequest ||= authHttp
        .post("/api/v1/auth/refresh")
        .finally(() => {
          refreshRequest = null;
        });

      try {
        await refreshRequest;
      } catch (refreshError) {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
        return Promise.reject(refreshError);
      }
      return authHttp(originalRequest);
    }

    return Promise.reject(error);
  },
);

export function onSessionExpired(handler) {
  window.addEventListener(SESSION_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
}

export async function loginRequest({ username, password }) {
  const response = await authHttp.post("/api/v1/auth/login", {
    username,
    password,
  });
  // Login rotates the CSRF cookie from anonymous to the new session binding.
  invalidateCsrfToken();
  return response.data.data.user;
}

export async function getCurrentUser() {
  const response = await authHttp.get("/api/v1/auth/me");
  return response.data.data.user;
}

export async function logoutRequest() {
  try {
    await authHttp.post("/api/v1/auth/logout");
  } finally {
    invalidateCsrfToken();
  }
}
