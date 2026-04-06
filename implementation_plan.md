# Credit Card Balance Overview & Payment Analysis

Build a web application for tracking and analyzing credit card payments against bank account balances. It features a dashboard to track multiple bank/credit accounts, snapshot-based "Analyses" with real-time balance calculations, and multi-payment support.

## User Review Required

> [!IMPORTANT]
> Please review the **DynamoDB Single-Table Design** below. Storing snapshots for "Analysis" records requires decoupling them from the live Account configurations so renaming accounts doesn't break historical analyses. Please let me know if you would like me to use a local dynamodb instance (like `aioboto3` mock or `boto3` dict wrapper) to develop and verify this locally, or if you will be providing AWS credentials. I will default to providing mock DB capabilities for local development and real `boto3` capabilities for production.

> [!NOTE]
> Since we use TailwindCSS, I am planning to serve Tailwind via their CDN for quick development without needing a Node.js build step, but this limits some customization. If you prefer a build process with `npm` (to generate the CSS), let me know.

## Proposed Changes

### Backend Setup (FastAPI & Deployment)

- Use **FastAPI** to serve both the API endpoints and the HTMX-driven HTML templates.
- Use **Jinja2Templates** for server-side HTML rendering.
- Wrap the FastAPI instance with **Mangum** to deploy on AWS Lambda via a Function URL.

### DynamoDB Single-Table Design

We will use a single table with a Partition Key (`PK`) and Sort Key (`SK`).

| Entity | PK | SK | Key Attributes |
|---|---|---|---|
| **Account** | `ACCOUNT#<id>` | `ACCOUNT#<id>` | `name`, `type` (Bank OR Credit) |
| **Analysis** | `ANALYSIS#<id>` | `META` | `title`, `date`, `global_bank_balance`, `global_credit_balance` |
| **Analysis Bank Snapshot** | `ANALYSIS#<id>` | `BANK#<account_id>` | `account_name` (snapshot), `starting_balance` |
| **Analysis Credit Snapshot**| `ANALYSIS#<id>` | `CREDIT#<account_id>` | `card_name` (snapshot), `statement_balance` |
| **Analysis Payment** | `ANALYSIS#<id>` | `CREDIT#<credit_account_id>#PAY#<pay_id>`| `payment_amount`, `source_bank_id`, `source_bank_name`, `date` |

*Note: Calculations (Ending balances) can be computed dynamically by the backend when fetching the analysis or stored in the `META` / Snapshot rows whenever a payment is added/modified.*

### Frontend Layout

#### `templates/base.html`

- Contains common layout, Tailwind CSS via CDN, HTMX script, and navigation.

#### `templates/index.html` (Homepage)

- Lists past saved analyses and a "New Analysis" button.

#### `templates/accounts.html`

- Lists current Bank and Credit Card accounts.
- HTMX forms to create, edit, or delete accounts inline.

#### `templates/analysis.html`

- The core screen. Includes:
  - Header with Title and Date.
  - **Bank Table:** Lists bank accounts selected for this analysis, starting balances, and calculated ending balances.
  - **Credit Table:** Lists credit cards, statement balances, and a sub-table/section for associating multiple payments (linking to a Bank Account).
  - Real-time updates: When a payment is added or changed, it triggers an HTMX request to update the specific Credit Card's ending balance and the global sums.

#### `templates/partials/`

- Various HTMX partials: `_bank_row.html`, `_credit_row.html`, `_payment_row.html`, `_totals.html` to allow updating granular chunks of the UI rapidly.

## Open Questions

1. **Local Development:** Do you want me to spin up a local instance of DynamoDB using Docker (`amazon/dynamodb-local`) for development and testing, or just write a simple in-memory python dictionary store to simulate DynamoDB first to get the app working?
2. **Tailwind:** Is using the Tailwind CSS CDN acceptable, or do you want a local `npm` build process for CSS?
3. **Draft Analysis vs Saved Analysis:** Should an Analysis be created in the DB as soon as the user clicks "New Analysis" (so auto-saving works instantly via HTMX), or should it remain purely in-memory/client-side until they hit "Save"? (Pre-creating the DB record makes HTMX updates vastly easier to implement).

## Verification Plan

### Automated Tests

- Optionally, if we write any Pytest endpoints to mock the DB, we can run them.

### Manual Verification

- We will run the FastAPI server locally (`uvicorn app.main:app --reload`).
- We will interact with the Accounts page to ensure we can create banks/cards.
- We will create an Analysis, add starting balances and statement balances.
- We will add multiple payment rows to a credit card, mapped to a bank account, and verify the HTMX updates correctly refresh the Bank Ending Balance, Credit Card Ending Balance, and Global Totals without a full page refresh.
