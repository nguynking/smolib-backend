# smolib backend

## Supabase auth

Set these environment variables before starting the API:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` (or `SUPABASE_KEY` / `SUPABASE_SERVICE_ROLE_KEY`)

Available auth endpoints:

- `POST /auth/sign-up` - create a user with email/password
- `POST /auth/sign-in` - sign in with email/password
- `POST /auth/refresh` - refresh a session from a refresh token
- `GET /auth/me` - get current user from `Authorization: Bearer <access_token>`
- `POST /auth/sign-out` - revoke user sessions (requires bearer token)
