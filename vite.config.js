import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// This predictable nonce is intentionally development-only. It lets Vite tag
// its injected React Fast Refresh preamble without enabling every inline script.
// Production must generate a unique nonce per HTTP response or omit nonces,
// which is what this static build does.
const DEVELOPMENT_CSP_NONCE = "vite-development-only";

function createContentSecurityPolicy({ development = false } = {}) {
  return [
    "default-src 'self'",
    development
      ? `script-src 'self' 'nonce-${DEVELOPMENT_CSP_NONCE}'`
      : "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    // WebSocket schemes are required only by Vite's development HMR client.
    development
      ? "connect-src 'self' ws: wss:"
      : "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
  ].join("; ");
}

function environmentCspMetaPlugin(policy) {
  return {
    name: "environment-csp-meta",
    transformIndexHtml: {
      order: "pre",
      handler() {
        return [
          {
            tag: "meta",
            attrs: {
              "http-equiv": "Content-Security-Policy",
              content: policy,
            },
            injectTo: "head-prepend",
          },
        ];
      },
    },
  };
}

export default defineConfig(({ command }) => {
  const isDevelopment = command === "serve";
  const developmentPolicy = createContentSecurityPolicy({ development: true });
  const productionPolicy = createContentSecurityPolicy();
  const activePolicy = isDevelopment ? developmentPolicy : productionPolicy;

  return {
    plugins: [environmentCspMetaPlugin(activePolicy), react()],
    // Vite applies this nonce to its injected React Fast Refresh preamble and
    // other generated tags. It is never embedded in the production build.
    html: isDevelopment
      ? { cspNonce: DEVELOPMENT_CSP_NONCE }
      : undefined,
    server: {
      // Keeping browser calls same-origin is required by SameSite=Strict and
      // avoids the localhost-vs-127.0.0.1 cookie mismatch.
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: false,
          ws: true,
        },
      },
      headers: {
        "Content-Security-Policy": developmentPolicy,
      },
    },
    preview: {
      headers: {
        "Content-Security-Policy": productionPolicy,
      },
    },
  };
});
