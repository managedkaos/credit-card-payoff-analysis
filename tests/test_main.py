"""Tests for FastAPI route handlers in main.py.

All database calls are mocked so these tests verify routing logic,
status codes, and template rendering without touching DynamoDB.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app

MOCK_ACCOUNT_BANK = {"id": "bank-1", "name": "Chase Checking", "type": "bank"}
MOCK_ACCOUNT_CREDIT = {"id": "credit-1", "name": "Amex Gold", "type": "credit"}
MOCK_ACCOUNT_LOAN = {"id": "loan-1", "name": "Auto Loan", "type": "loan"}
MOCK_ACCOUNTS = [MOCK_ACCOUNT_BANK, MOCK_ACCOUNT_CREDIT, MOCK_ACCOUNT_LOAN]

MOCK_ANALYSIS = {
    "id": "analysis-1",
    "title": "April Payoff",
    "date": "2026-04-06",
    "snapshots": {"bank-1": {"name": "Chase Checking", "starting_balance": 5000.0}},
    "credit_snapshots": {
        "credit-1": {"name": "Amex Gold", "statement_balance": 1200.0}
    },
    "removed_accounts": [],
    "payments": [
        {
            "id": "pay-1",
            "credit_id": "credit-1",
            "bank_id": "bank-1",
            "amount": 500.0,
            "date": "2026-04-06",
        }
    ],
}

MOCK_PAYMENT = {
    "id": "pay-new",
    "credit_id": "credit-1",
    "bank_id": "bank-1",
    "amount": 250.0,
    "date": "2026-04-06",
}


@pytest.fixture()
def client():
    """Provide a TestClient for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------


@patch("main.db.get_analyses", return_value=[MOCK_ANALYSIS])
def test_home_returns_200(mock_get, client):
    """GET / should render the homepage."""
    response = client.get("/")
    assert response.status_code == 200
    mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# Analysis CRUD
# ---------------------------------------------------------------------------


@patch("main.db.create_analysis", return_value=MOCK_ANALYSIS)
def test_create_new_analysis_redirects(mock_create, client):
    """POST /analyses/new should redirect to the new analysis."""
    response = client.post("/analyses/new", follow_redirects=False)
    assert response.status_code == 303
    assert f"/analyses/{MOCK_ANALYSIS['id']}" in response.headers["location"]
    mock_create.assert_called_once()


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
def test_view_analysis_returns_200(mock_analysis, mock_accounts, client):
    """GET /analyses/{id} should render the analysis page."""
    response = client.get("/analyses/analysis-1")
    assert response.status_code == 200
    mock_analysis.assert_called_once_with("analysis-1")


@patch("main.db.get_analysis", return_value=None)
def test_view_analysis_not_found(mock_analysis, client):
    """GET /analyses/{id} with a bad ID should return 404."""
    response = client.get("/analyses/nonexistent")
    assert response.status_code == 404


@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.save_analysis")
def test_update_analysis_title(mock_save, mock_get, client):
    """POST update_title should call save_analysis with the new title."""
    response = client.post(
        "/analyses/analysis-1/update_title", data={"title": "New Title"}
    )
    assert response.status_code == 200
    mock_save.assert_called_once_with("analysis-1", {"title": "New Title"})


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
def test_list_accounts(mock_get, client):
    """GET /accounts should render the accounts page."""
    response = client.get("/accounts")
    assert response.status_code == 200
    mock_get.assert_called_once()


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.create_account", return_value=MOCK_ACCOUNT_BANK)
def test_add_account(mock_create, mock_get, client):
    """POST /accounts should create the account and return the list partial."""
    response = client.post("/accounts", data={"name": "Savings", "type": "bank"})
    assert response.status_code == 200
    mock_create.assert_called_once_with("Savings", "bank")


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.create_account", return_value=MOCK_ACCOUNT_LOAN)
def test_add_loan_account(mock_create, mock_get, client):
    """POST /accounts with type=loan should create the account."""
    response = client.post("/accounts", data={"name": "Auto Loan", "type": "loan"})
    assert response.status_code == 200
    mock_create.assert_called_once_with("Auto Loan", "loan")


def test_add_account_invalid_type(client):
    """POST /accounts with invalid type should return 400."""
    response = client.post("/accounts", data={"name": "Bad", "type": "investment"})
    assert response.status_code == 400


@patch("main.db.get_accounts", return_value=[])
@patch("main.db.delete_account", return_value=True)
def test_delete_account(mock_delete, mock_get, client):
    """POST /accounts/{id}/delete should delete and return the list partial."""
    response = client.post("/accounts/bank-1/delete")
    assert response.status_code == 200
    mock_delete.assert_called_once_with("bank-1")


@patch("main.db.get_account", return_value=MOCK_ACCOUNT_BANK)
def test_edit_account(mock_get, client):
    """GET /accounts/{id}/edit should return the edit form partial."""
    response = client.get("/accounts/bank-1/edit")
    assert response.status_code == 200
    mock_get.assert_called_once_with("bank-1")


@patch("main.db.get_account", return_value=None)
def test_edit_account_not_found(mock_get, client):
    """GET /accounts/{id}/edit for missing account should return 404."""
    response = client.get("/accounts/bad-id/edit")
    assert response.status_code == 404


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.update_account", return_value=MOCK_ACCOUNT_BANK)
def test_update_account(mock_update, mock_get, client):
    """POST /accounts/{id}/update should rename and return the list partial."""
    response = client.post("/accounts/bank-1/update", data={"name": "Renamed"})
    assert response.status_code == 200
    mock_update.assert_called_once_with("bank-1", "Renamed")


# ---------------------------------------------------------------------------
# Analysis <-> Account management
# ---------------------------------------------------------------------------


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.add_account_to_analysis", return_value=True)
def test_add_account_to_analysis(mock_add, mock_analysis, mock_accounts, client):
    """POST add_account should call add_account_to_analysis."""
    response = client.post(
        "/analyses/analysis-1/add_account", data={"account_id": "bank-1"}
    )
    assert response.status_code == 200
    mock_add.assert_called_once_with("analysis-1", "bank-1")


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.remove_account_from_analysis", return_value=True)
def test_remove_account_from_analysis(
    mock_remove, mock_analysis, mock_accounts, client
):
    """POST remove_account should call remove_account_from_analysis."""
    response = client.post(
        "/analyses/analysis-1/remove_account", data={"account_id": "credit-1"}
    )
    assert response.status_code == 200
    mock_remove.assert_called_once_with("analysis-1", "credit-1")


# ---------------------------------------------------------------------------
# Snapshot updates
# ---------------------------------------------------------------------------


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.update_snapshot", return_value=True)
def test_update_snapshot_bank(mock_update, mock_analysis, mock_accounts, client):
    """POST update_snapshot for a bank should update starting_balance."""
    response = client.post(
        "/analyses/analysis-1/update_snapshot",
        data={"account_id": "bank-1", "amount": "6000.00", "type": "bank"},
    )
    assert response.status_code == 200
    mock_update.assert_called_once_with("analysis-1", "bank-1", "bank", 6000.0)


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.update_snapshot", return_value=True)
def test_update_snapshot_credit(mock_update, mock_analysis, mock_accounts, client):
    """POST update_snapshot for a credit should update statement_balance."""
    response = client.post(
        "/analyses/analysis-1/update_snapshot",
        data={"account_id": "credit-1", "amount": "800.00", "type": "credit"},
    )
    assert response.status_code == 200
    mock_update.assert_called_once_with("analysis-1", "credit-1", "credit", 800.0)


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.update_snapshot", return_value=True)
def test_update_snapshot_loan(mock_update, mock_analysis, mock_accounts, client):
    """POST update_snapshot for a loan should update statement_balance."""
    response = client.post(
        "/analyses/analysis-1/update_snapshot",
        data={"account_id": "loan-1", "amount": "15000.00", "type": "loan"},
    )
    assert response.status_code == 200
    mock_update.assert_called_once_with("analysis-1", "loan-1", "loan", 15000.0)


@patch("main.db.get_analysis", return_value=None)
@patch("main.db.update_snapshot", return_value=True)
def test_update_snapshot_analysis_not_found(mock_update, mock_analysis, client):
    """POST update_snapshot when analysis is missing should return 404."""
    response = client.post(
        "/analyses/bad-id/update_snapshot",
        data={"account_id": "bank-1", "amount": "100", "type": "bank"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.add_payment", return_value=MOCK_PAYMENT)
def test_add_payment(mock_add, mock_analysis, mock_accounts, client):
    """POST /analyses/{id}/payments should add a payment."""
    response = client.post(
        "/analyses/analysis-1/payments",
        data={
            "credit_id": "credit-1",
            "bank_id": "bank-1",
            "amount": "250.00",
            "p_date": "2026-04-06",
        },
    )
    assert response.status_code == 200
    mock_add.assert_called_once_with(
        "analysis-1", "credit-1", "bank-1", 250.0, "2026-04-06"
    )


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.add_payment", return_value=MOCK_PAYMENT)
def test_add_payment_default_date(mock_add, mock_analysis, mock_accounts, client):
    """POST /analyses/{id}/payments without p_date should default to today."""
    response = client.post(
        "/analyses/analysis-1/payments",
        data={"credit_id": "credit-1", "bank_id": "bank-1", "amount": "100.00"},
    )
    assert response.status_code == 200
    call_args = mock_add.call_args
    assert call_args[0][4] is not None  # date was filled in


@patch("main.db.get_accounts", return_value=MOCK_ACCOUNTS)
@patch("main.db.get_analysis", return_value=MOCK_ANALYSIS)
@patch("main.db.remove_payment", return_value=True)
def test_remove_payment(mock_remove, mock_analysis, mock_accounts, client):
    """POST /analyses/{id}/payments/{pid}/delete should remove the payment."""
    response = client.post("/analyses/analysis-1/payments/pay-1/delete")
    assert response.status_code == 200
    mock_remove.assert_called_once_with("analysis-1", "pay-1")
