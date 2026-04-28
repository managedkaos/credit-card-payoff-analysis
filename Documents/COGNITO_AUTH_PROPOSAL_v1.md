# AWS Cognito Authentication Proposal

## Application Summary

This is a **FastAPI** web application for tracking and analyzing credit card payments against bank account balances. Key characteristics:

- **Framework:** FastAPI with Jinja2 templates and HTMX for interactive UI
- **Database:** DynamoDB single-table design (accounts, analyses, payments)
- **Deployment:** AWS Lambda via **Mangum** adapter, exposed through a Function URL or API Gateway
- **Frontend:** Server-rendered HTML with Tailwind CSS (CDN) and HTMX — no SPA framework
- **Current auth:** None — all routes are publicly accessible

The application handles sensitive financial data (bank balances, credit card statements, payment records), making authentication essential before production deployment.

---

## Recommended Approach: Cognito Hosted UI with OAuth2/OIDC

Given that this is a server-rendered application (not a SPA), the best integration pattern is the **OAuth2 Authorization Code flow** using Cognito's Hosted UI. This keeps token management server-side, avoids exposing tokens to the browser, and requires minimal frontend changes.

### Why This Approach

| Alternative | Why Not |
|---|---|
| Cognito + Amplify JS SDK | Designed for SPAs; overkill for server-rendered HTMX app |
| Custom login form + Cognito API (InitiateAuth) | Requires building/maintaining login UI, MFA flows, password reset, etc. |
| API Gateway Cognito Authorizer | Works for JSON APIs but doesn't integrate well with HTML responses and redirects |
| **Hosted UI + Authorization Code Flow** | **Best fit** — delegates login UI to Cognito, tokens stay server-side, minimal frontend changes |

---

## Architecture

```
Browser
  │
  ├── GET /accounts ──────────────► Lambda (FastAPI)
  │                                    │
  │                                    ├── Check session cookie
  │                                    │     ├── Valid → serve page
  │                                    │     └── Invalid/missing → redirect to Cognito Hosted UI
  │
  ├── Cognito Hosted UI ◄──────────── 302 Redirect
  │     │
  │     └── User logs in
  │           │
  │           └── 302 redirect to /auth/callback?code=XXXX
  │
  ├── GET /auth/callback ──────────► Lambda (FastAPI)
  │                                    │
  │                                    ├── Exchange code for tokens (Cognito Token endpoint)
  │                                    ├── Validate ID token
  │                                    ├── Create session (signed cookie or DynamoDB session)
  │                                    └── 302 redirect to original page
  │
  └── Subsequent requests use session cookie
```

---

## Implementation Plan

### Phase 1: AWS Infrastructure Setup

#### Cognito User Pool

- Create a User Pool with email as the primary sign-in attribute
- Enable self-service sign-up (or disable if invite-only)
- Configure password policy, MFA (optional), and email verification
- Configure the Hosted UI domain (e.g., `payoff-analysis.auth.us-east-1.amazoncognito.com`)

#### Cognito App Client

- Create an App Client with a client secret (confidential client for server-side flow)
- Configure callback URL: `https://<your-domain>/auth/callback`
- Configure sign-out URL: `https://<your-domain>/`
- Allowed OAuth flows: Authorization Code Grant
- Allowed OAuth scopes: `openid`, `email`, `profile`

#### Environment Variables (added to Lambda)

```
COGNITO_USER_POOL_ID=us-east-1_XXXXXXX
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_CLIENT_SECRET=<stored in Secrets Manager or env>
COGNITO_DOMAIN=https://payoff-analysis.auth.us-east-1.amazoncognito.com
APP_DOMAIN=https://your-app-domain.com
SESSION_SECRET=<random 32+ byte key for signing cookies>
```

### Phase 2: Backend Changes

#### New Dependencies

Add to `requirements.txt`:

```
python-jose[cryptography]
httpx
itsdangerous
```

- `python-jose` — JWT decoding and verification of Cognito ID tokens
- `httpx` — async HTTP client for token exchange with Cognito
- `itsdangerous` — signed cookie sessions

#### New Module: `auth.py`

Responsibilities:
1. **Session management** — sign/verify session cookies containing the user's sub (Cognito user ID) and email
2. **Token exchange** — POST to Cognito's `/oauth2/token` endpoint to exchange the authorization code for ID/access/refresh tokens
3. **Token validation** — verify the ID token signature against Cognito's JWKS
4. **Middleware/dependency** — a FastAPI dependency that checks for a valid session and redirects to login if missing

```python
# Proposed auth.py structure (pseudocode)

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

def get_current_user(request: Request):
    """FastAPI dependency — extracts user from session cookie or redirects to login."""
    session = verify_session_cookie(request)
    if not session:
        return RedirectResponse(build_cognito_login_url(request.url))
    return session["user"]

def build_cognito_login_url(redirect_after: str) -> str:
    """Construct the Hosted UI authorize URL with state parameter."""
    ...

async def exchange_code_for_tokens(code: str) -> dict:
    """POST to Cognito /oauth2/token, return decoded ID token claims."""
    ...

def verify_session_cookie(request: Request) -> dict | None:
    """Decode and verify the signed session cookie."""
    ...

def create_session_cookie(user_claims: dict) -> str:
    """Create a signed cookie containing user sub, email, and expiry."""
    ...
```

#### New Routes

```python
@app.get("/auth/login")
async def login(request: Request):
    """Redirect to Cognito Hosted UI."""
    ...

@app.get("/auth/callback")
async def auth_callback(request: Request, code: str, state: str):
    """Exchange authorization code for tokens, create session, redirect."""
    ...

@app.get("/auth/logout")
async def logout(request: Request):
    """Clear session cookie and redirect to Cognito logout endpoint."""
    ...
```

#### Protecting Existing Routes

Use a FastAPI dependency on all routes that require authentication:

```python
from auth import get_current_user

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user=Depends(get_current_user)):
    ...
```

Alternatively, apply via middleware to protect all routes except `/auth/*` paths.

### Phase 3: Data Isolation (Multi-Tenancy)

Once users are authenticated, each user's data should be isolated. The DynamoDB single-table design makes this straightforward by prefixing the partition key with the user's Cognito `sub`:

| Current PK | New PK |
|---|---|
| `ACCOUNT#<id>` | `USER#<sub>#ACCOUNT#<id>` |
| `ANALYSIS#<id>` | `USER#<sub>#ANALYSIS#<id>` |

This ensures one user cannot access another user's accounts or analyses. The `database.py` functions would accept a `user_id` parameter:

```python
def get_accounts(user_id: str) -> list:
    table = _get_table()
    response = table.scan(
        FilterExpression=Attr("PK").begins_with(f"USER#{user_id}#ACCOUNT#")
            & Attr("SK").begins_with("ACCOUNT#")
    )
    ...
```

> **Note:** If multi-tenancy is not needed (single-user or shared workspace), this phase can be deferred and all users would see the same data.

### Phase 4: Frontend Changes

Minimal changes required:

1. **`templates/base.html`** — Add a user indicator and logout link to the navigation bar:

```html
<div class="flex items-center space-x-4">
    <span class="text-sm text-gray-600">{{ user.email }}</span>
    <a href="/auth/logout" class="text-sm text-red-600 hover:text-red-800">Sign out</a>
</div>
```

2. **Login page** — Not needed if using the Hosted UI (Cognito provides it). Optionally add a branded `/auth/login` landing page with a "Sign in" button that redirects to Cognito.

3. **Error handling** — If a session expires mid-interaction (e.g., during an HTMX request), return a `HX-Redirect` header to send the user to login:

```python
response.headers["HX-Redirect"] = "/auth/login"
```

---

## Session Storage Options

| Option | Pros | Cons |
|---|---|---|
| **Signed cookie (itsdangerous)** | Simple, no extra infra, stateless Lambda-friendly | Cookie size limited (~4KB), can't revoke individual sessions |
| **DynamoDB session table** | Revocable, stores more data, survives cookie clears | Extra DynamoDB reads per request, TTL management |
| **Encrypted cookie (Fernet)** | Confidential + tamper-proof, still stateless | Same size limits as signed cookies |

**Recommendation:** Start with **signed cookies** (itsdangerous `URLSafeTimedSerializer`). Store only the user `sub`, email, and session expiry. Set the cookie `HttpOnly`, `Secure`, `SameSite=Lax`. If session revocation becomes a requirement, migrate to DynamoDB-backed sessions.

---

## Lambda-Specific Considerations

1. **Cold starts** — JWKS (JSON Web Key Set) fetching from Cognito adds latency on cold starts. Cache the JWKS in a module-level variable (Lambda reuses execution contexts).

2. **Function URL vs API Gateway:**
   - **Function URL:** Simpler, free, but lacks built-in WAF, custom domain requires CloudFront. The auth callback URL must match exactly.
   - **API Gateway (HTTP API):** Supports custom domains natively, can add a JWT authorizer as a backup layer, integrates with WAF. Adds cost but is more production-ready.

3. **Cookie domain** — If using CloudFront + Function URL, ensure the cookie domain matches the CloudFront distribution domain.

4. **Secrets management** — Store `COGNITO_CLIENT_SECRET` and `SESSION_SECRET` in AWS Secrets Manager or SSM Parameter Store (SecureString), not in Lambda environment variables directly.

---

## Security Considerations

- **CSRF protection** — The `state` parameter in the OAuth flow prevents CSRF on login. For form submissions (HTMX POST requests), use `SameSite=Lax` cookies combined with origin/referer checking.
- **Token refresh** — Store the refresh token in the session. Before expiry, use it to obtain new ID/access tokens without forcing re-login.
- **Session expiry** — Set session duration to match the Cognito refresh token validity (default 30 days). Shorter sessions (e.g., 8 hours) for higher security.
- **HTTPS only** — All cookies must be `Secure` flagged. Lambda Function URLs and API Gateway enforce HTTPS by default.

---

## Estimated Effort

| Phase | Effort | Dependencies |
|---|---|---|
| Phase 1: AWS Infra | 1-2 hours | AWS Console or IaC (CloudFormation/Terraform) |
| Phase 2: Backend auth module | 3-4 hours | `auth.py`, route changes, dependency wiring |
| Phase 3: Multi-tenancy | 2-3 hours | DynamoDB key refactor, database.py changes, data migration |
| Phase 4: Frontend | 1 hour | Template updates |
| Testing & debugging | 2-3 hours | End-to-end flow, token validation, edge cases |

**Total: ~10-13 hours**

---

## Alternatives Considered but Not Recommended

### 1. API Gateway JWT Authorizer (built-in)

API Gateway HTTP APIs can validate JWTs natively without any application code. However, this approach:
- Returns JSON 401 responses, which breaks the HTMX/HTML flow
- Cannot set/read cookies or manage sessions
- Requires the frontend to handle token storage (not suitable for server-rendered apps)

### 2. AWS IAM Authentication (SigV4)

Appropriate for machine-to-machine or internal APIs, not for end-user browser access.

### 3. Third-party Auth (Auth0, Clerk, etc.)

Viable but adds external dependency and cost when Cognito is already in the AWS ecosystem alongside Lambda and DynamoDB.

---

## Next Steps

1. Confirm whether multi-tenancy (Phase 3) is needed or if this is a single-user/shared app
2. Decide on Function URL vs API Gateway for production
3. Choose whether to allow self-service registration or admin-only user creation
4. Set up Cognito User Pool (manually or via IaC)
5. Implement `auth.py` and wire up the routes
