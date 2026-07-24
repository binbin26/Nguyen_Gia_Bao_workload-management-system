# Cookie authentication, CSRF, CSP, and HTML sanitization

## Browser/API flow

1. The SPA calls `GET /api/v1/auth/csrf`. FastAPI sets a readable CSRF cookie
   and returns the same signed token in JSON.
2. The Axios request interceptor adds that value as `X-CSRF-Token` to every
   `POST`, `PUT`, `PATCH`, and `DELETE` request.
3. `POST /api/v1/auth/login` returns only public user metadata in JSON. Access
   and refresh JWTs are sent exclusively through `Set-Cookie` with `HttpOnly`,
   `Secure`, `SameSite=Strict`, host-only scope, and `Path=/`.
4. The SPA calls `GET /api/v1/auth/me` when it boots. A 401 triggers exactly one
   refresh request, then Axios retries the original request.
5. Refresh tokens are one-time tokens. FastAPI atomically consumes the MongoDB
   `refresh_sessions` record and rotates both JWTs. Replaying an old refresh
   token returns 401.
6. Logout revokes the refresh session and expires all three cookies.

No access or refresh token is written to `localStorage`, `sessionStorage`, or
React state.

## Deployment requirements

- Serve the site over HTTPS and keep `COOKIE_SECURE=true`.
- Put the React app and `/api` on the same site. The included Vite development
  proxy demonstrates the expected route shape. For example, a production
  reverse proxy can serve `https://workforce.example.com/` and forward
  `https://workforce.example.com/api/*` to FastAPI.
- Replace all `change-me`/`replace-with` values with independent, randomly
  generated secrets of at least 32 bytes.
- Keep `CORS_ALLOWED_ORIGINS` as an exact JSON allow-list. Do not use `*` with
  credentialed requests.
- Configure the production static web server/CDN to emit the CSP from
  `vite.config.js`. The generated HTML meta policy is only a fallback and
  cannot enforce every directive (notably `frame-ancestors`).
- If local HTTPS is unavailable, `COOKIE_SECURE=false` may be used only in an
  isolated development environment. It must never be deployed.

## Rendering user-authored HTML

Plain text should be rendered normally because React escapes it:

```jsx
<p>{userInput}</p>
```

When product requirements explicitly allow rich HTML, use the single sanitized
boundary in `src/components/SafeHtml.jsx`:

```jsx
import SafeHtml from "./components/SafeHtml";

<SafeHtml html={userInput} className="prose" />
```

`SafeHtml` applies a narrow tag/attribute allow-list before
`dangerouslySetInnerHTML`. Do not concatenate or alter its sanitized result
afterward, and do not create another direct `dangerouslySetInnerHTML` call site.

## CSP policy

The backend middleware and Vite both apply a policy that:

- permits scripts only from the same origin and blocks inline/eval scripts;
- blocks plugins, framing, external form submissions, and base-tag injection;
- restricts AJAX, images, fonts, and other resources to known sources;
- allows inline CSS temporarily because existing React components use style
  attributes. This exception is scoped to `style-src` and does not weaken
  `script-src`.

In development only, `vite.config.js` uses `html.cspNonce` to add the
`vite-development-only` nonce to Vite's injected React Fast Refresh preamble.
The development CSP permits that exact nonce and HMR WebSocket connections; it
does not enable arbitrary inline scripts with `'unsafe-inline'`. Production
builds omit the development nonce and retain `script-src 'self'`.

The internal cron endpoint is exempt from CSRF because it does not use browser
cookies and is protected by `X-Internal-Secret`. All browser-facing mutation
routes, including login, refresh, and logout, require CSRF validation.
