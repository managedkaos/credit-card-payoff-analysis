# AWS Cognito Authentication Proposal (v2)

## Application Summary

This is a **FastAPI** web application for tracking and analyzing credit card payments against bank account balances. Key characteristics:

- **Framework:** FastAPI with Jinja2 templates and HTMX for interactive UI
- **Database:** DynamoDB single-table design (accounts, analyses, payments)
- **Deployment:** AWS Lambda via **Mangum** adapter
- **Frontend:** Server-rendered HTML with Tailwind CSS (CDN) and HTMX — no SPA framework
- **Current auth:** None — all routes are publicly accessible

The application handles sensitive financial data (bank balances, credit card statements, payment records), making authentication essential before production deployment.

### Key Decisions (v2)

| Decision | Outcome |
|---|---|
| Multi-tenancy | **Yes** — each user's data will be fully isolated |
| Self-registration | **No** for initial release (admin-created users only); may be enabled later |
| Deployment target | See [Function URL vs API Gateway comparison](#function-url-vs-api-gateway-comparison) below |

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
  │                                    │     ├── Valid → serve page (scoped to user)
  │                                    │     └── Invalid/missing → redirect to Cognito Hosted UI
  │
  ├── Cognito Hosted UI ◄──────────── 302 Redirect
  │     │
  │     └── User logs in (admin-created account)
  │           │
  │           └── 302 redirect to /auth/callback?code=XXXX
  │
  ├── GET /auth/callback ──────────► Lambda (FastAPI)
  │                                    │
  │                                    ├── Exchange code for tokens (Cognito Token endpoint)
  │                                    ├── Validate ID token
  │                                    ├── Extract user sub → used as tenant partition key
  │                                    ├── Create session (signed cookie)
  │                                    └── 302 redirect to original page
  │
  └── Subsequent requests use session cookie (user sub scopes all DB queries)
```

---

## Function URL vs API Gateway Comparison

Both options expose the Lambda function to the internet. The right choice depends on production requirements around custom domains, security layers, and cost tolerance.

### Lambda Function URL

| Aspect | Details |
|---|---|
| **Cost** | Free (included with Lambda invocations) |
| **Setup complexity** | Minimal — one toggle in Lambda config |
| **Custom domain** | Requires CloudFront distribution in front of the Function URL |
| **WAF integration** | Not directly supported; requires CloudFront + WAF |
| **Throttling/rate limiting** | No built-in rate limiting; must implement in application code or add CloudFront |
| **Auth callback** | Must use the raw `*.lambda-url.*.on.aws` URL or CloudFront domain |
| **CORS** | Configurable on the Function URL |
| **Monitoring** | CloudWatch only; no request-level access logs without CloudFront |

### API Gateway (HTTP API)

| Aspect | Details |
|---|---|
| **Cost** | $1.00 per million requests + data transfer (HTTP API pricing) |
| **Setup complexity** | Moderate — create API, routes, stage, integration |
| **Custom domain** | Native support via API Gateway custom domain mappings |
| **WAF integration** | Direct WAF attachment (regional WAF) |
| **Throttling/rate limiting** | Built-in configurable throttling per route and per stage |
| **Auth callback** | Clean custom domain URL works directly |
| **JWT authorizer** | Can add as an additional defense layer (validates tokens at the gateway before Lambda is invoked) |
| **Monitoring** | Access logs, CloudWatch metrics, X-Ray tracing built in |

### Side-by-Side Summary

| Criteria | Function URL | API Gateway (HTTP API) |
|---|---|---|
| Cost (low traffic <1M req/mo) | Free | ~$1/month |
| Cost (high traffic 10M req/mo) | Free | ~$10/month |
| Custom domain ease | Hard (needs CloudFront) | Easy (native) |
| WAF/DDoS protection | Requires CloudFront | Built-in |
| Rate limiting | DIY | Built-in |
| Production readiness | MVP/internal tool | Production-grade |
| Path to future growth | Need to add CloudFront eventually | Already there |
| Cold start impact | None (direct invoke) | Negligible (HTTP API is lightweight) |

### Recommendation

- **For MVP / internal use with few users:** Function URL is sufficient. It's free and simple. Since users are admin-created (small, known user base), rate limiting and WAF are less critical initially.
- **For production with external-facing users:** API Gateway HTTP API is the better choice. The $1/month cost is negligible, and you gain custom domains, WAF, rate limiting, and observability out of the box.
- **Hybrid path:** Start with Function URL for development and early deployment. When you need a custom domain or WAF, add API Gateway in front (or CloudFront + Function URL). The application code (Mangum adapter) works identically with both — no code changes required to switch.

---

## Implementation Plan

### Phase 1: AWS Infrastructure Setup

#### Cognito User Pool

- Create a User Pool with email as the primary sign-in attribute
- **Disable self-service sign-up** — admins will create users via the AWS Console, CLI, or a future admin endpoint
- Configure password policy and email verification (Cognito sends a temporary password on user creation)
- Optionally enable MFA (can be enforced per-user or pool-wide)
- Configure the Hosted UI domain (e.g., `payoff-analysis.auth.us-east-1.amazoncognito.com`)
- Set `AdminCreateUserConfig.AllowAdminCreateUserOnly = true`

#### User Provisioning (Admin-Only)

Since self-registration is disabled, new users will be created via:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_XXXXXXX \
  --username user@example.com \
  --user-attributes Name=email,Value=user@example.com Name=email_verified,Value=true \
  --temporary-password "TempPass123!" \
  --message-action SUPPRESS  # or remove to send invite email
```

The user receives a temporary password and is prompted to set a new one on first login via the Hosted UI. A future admin panel or CLI tool can wrap this for convenience.

#### Future: Enabling Self-Registration

When self-registration is needed later, the changes are minimal:
1. Set `AllowAdminCreateUserOnly = false` on the User Pool
2. Optionally add a pre-sign-up Lambda trigger to restrict registration by email domain or require admin approval
3. Update the Hosted UI to show the "Sign Up" link

No application code changes are required — the Hosted UI automatically adapts.

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
COGNITO_CLIENT_SECRET=<stored in Secrets Manager>
COGNITO_DOMAIN=https://payoff-analysis.auth.us-east-1.amazoncognito.com
APP_DOMAIN=https://your-app-domain.com
SESSION_SECRET=<stored in Secrets Manager>
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
    return session["user"]  # Contains {"sub": "...", "email": "..."}

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

Each user's data will be fully isolated by prefixing the DynamoDB partition key with the user's Cognito `sub` (a stable, unique user identifier).

#### Updated DynamoDB Key Schema

| Entity | Current PK | New PK | SK (unchanged) |
|---|---|---|---|
| Account | `ACCOUNT#<id>` | `USER#<sub>#ACCOUNT#<id>` | `ACCOUNT#<id>` |
| Analysis META | `ANALYSIS#<id>` | `USER#<sub>#ANALYSIS#<id>` | `META` |
| Bank Snapshot | `ANALYSIS#<id>` | `USER#<sub>#ANALYSIS#<id>` | `BANK#<account_id>` |
| Credit Snapshot | `ANALYSIS#<id>` | `USER#<sub>#ANALYSIS#<id>` | `CREDIT#<account_id>` |
| Payment | `ANALYSIS#<id>` | `USER#<sub>#ANALYSIS#<id>` | `CREDIT#<cid>#PAY#<pid>` |

#### Changes to `database.py`

All public functions gain a `user_id: str` parameter. The user ID is passed from the authenticated route handler (extracted from the session):

```python
def get_accounts(user_id: str) -> list:
    """Return all accounts belonging to a specific user."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").begins_with(f"USER#{user_id}#ACCOUNT#")
    )
    ...

def create_account(user_id: str, name: str, acc_type: str) -> dict:
    acc_id = str(uuid.uuid4())
    table = _get_table()
    table.put_item(
        Item={
            "PK": f"USER#{user_id}#ACCOUNT#{acc_id}",
            "SK": f"ACCOUNT#{acc_id}",
            "name": name,
            "type": acc_type,
        }
    )
    ...

def get_analysis(user_id: str, analysis_id: str):
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}#ANALYSIS#{analysis_id}")
    )
    ...
```

#### Route Handler Changes

Each route passes `user["sub"]` to database functions:

```python
@app.get("/accounts", response_class=HTMLResponse)
async def list_accounts(request: Request, user=Depends(get_current_user)):
    accounts = db.get_accounts(user["sub"])
    return templates.TemplateResponse(...)
```

#### Data Migration Strategy

For existing data created before multi-tenancy:

1. Assign an "owner" user (the initial admin) in Cognito
2. Run a one-time migration script that prefixes all existing PKs with `USER#<admin-sub>#`
3. No data loss — just a key transformation

```python
# migration pseudocode
def migrate_existing_data(admin_sub: str):
    table = _get_table()
    response = table.scan()
    for item in response["Items"]:
        old_pk = item["PK"]
        if not old_pk.startswith("USER#"):
            new_pk = f"USER#{admin_sub}#{old_pk}"
            new_item = {**item, "PK": new_pk}
            table.put_item(Item=new_item)
            table.delete_item(Key={"PK": old_pk, "SK": item["SK"]})
```

#### Security Guarantees

- A user can only query/modify items where `PK` starts with their own `USER#<sub>#` prefix
- Even if a user guesses another user's analysis ID, the PK mismatch prevents access
- No additional authorization layer needed — tenant isolation is enforced at the data model level

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

2. **Cookie domain** — If using CloudFront + Function URL, ensure the cookie domain matches the CloudFront distribution domain.

3. **Secrets management** — Store `COGNITO_CLIENT_SECRET` and `SESSION_SECRET` in AWS Secrets Manager or SSM Parameter Store (SecureString), not in Lambda environment variables directly.

---

## Security Considerations

- **CSRF protection** — The `state` parameter in the OAuth flow prevents CSRF on login. For form submissions (HTMX POST requests), use `SameSite=Lax` cookies combined with origin/referer checking.
- **Token refresh** — Store the refresh token in the session. Before expiry, use it to obtain new ID/access tokens without forcing re-login.
- **Session expiry** — Set session duration to match the Cognito refresh token validity (default 30 days). Shorter sessions (e.g., 8 hours) for higher security.
- **HTTPS only** — All cookies must be `Secure` flagged. Lambda Function URLs and API Gateway enforce HTTPS by default.
- **Tenant isolation** — All database queries are scoped by user sub in the partition key, preventing cross-tenant data access.

---

## Estimated Effort

| Phase | Effort | Dependencies |
|---|---|---|
| Phase 1: AWS Infra (Cognito + deployment target) | 1-2 hours | AWS Console or IaC (CloudFormation/Terraform) |
| Phase 2: Backend auth module | 3-4 hours | `auth.py`, route changes, dependency wiring |
| Phase 3: Multi-tenancy | 2-3 hours | DynamoDB key refactor, database.py changes, data migration script |
| Phase 4: Frontend | 1 hour | Template updates |
| Testing & debugging | 2-3 hours | End-to-end flow, token validation, tenant isolation verification |

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

1. ~~Confirm whether multi-tenancy is needed~~ **Confirmed: yes**
2. ~~Choose whether to allow self-service registration~~ **Confirmed: admin-only initially**
3. Choose deployment target (Function URL for MVP or API Gateway for production)
4. Set up Cognito User Pool with `AllowAdminCreateUserOnly = true`
5. Implement `auth.py` and wire up the routes
6. Refactor `database.py` with user-scoped partition keys
7. Write and run data migration script for existing records
