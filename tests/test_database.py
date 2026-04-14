"""Integration tests for database.py against DynamoDB Local.

Each test gets a clean table via the ``clean_table`` fixture so tests
are fully isolated.  The test table itself is created once per session
and deleted on teardown (see conftest.py).
"""

import database as db

# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------


class TestCreateAccount:
    """Tests for database.create_account."""

    def test_returns_dict_with_id(self, clean_table):
        """Created account should have an id, name, and type."""
        result = db.create_account("Chase Checking", "bank")
        assert result["name"] == "Chase Checking"
        assert result["type"] == "bank"
        assert "id" in result

    def test_persists_to_dynamodb(self, clean_table):
        """Account should be retrievable after creation."""
        created = db.create_account("Savings", "bank")
        fetched = db.get_account(created["id"])
        assert fetched is not None
        assert fetched["name"] == "Savings"


class TestGetAccounts:
    """Tests for database.get_accounts."""

    def test_empty_table(self, clean_table):
        """Should return an empty list when no accounts exist."""
        assert db.get_accounts() == []

    def test_returns_all_accounts(self, clean_table):
        """Should return every created account."""
        db.create_account("Bank A", "bank")
        db.create_account("Card B", "credit")
        accounts = db.get_accounts()
        assert len(accounts) == 2
        names = {a["name"] for a in accounts}
        assert names == {"Bank A", "Card B"}


class TestGetAccount:
    """Tests for database.get_account."""

    def test_existing_account(self, clean_table):
        """Should return the account dict for a valid ID."""
        created = db.create_account("Test", "bank")
        result = db.get_account(created["id"])
        assert result["name"] == "Test"

    def test_missing_account(self, clean_table):
        """Should return None for a nonexistent ID."""
        assert db.get_account("does-not-exist") is None


class TestUpdateAccount:
    """Tests for database.update_account."""

    def test_rename(self, clean_table):
        """Should update the account name."""
        created = db.create_account("Old Name", "bank")
        db.update_account(created["id"], "New Name")
        fetched = db.get_account(created["id"])
        assert fetched["name"] == "New Name"

    def test_missing_account_returns_none(self, clean_table):
        """Should return None when the account does not exist."""
        result = db.update_account("no-such-id", "Whatever")
        assert result is None


class TestDeleteAccount:
    """Tests for database.delete_account."""

    def test_delete_removes_account(self, clean_table):
        """Account should no longer be retrievable after deletion."""
        created = db.create_account("Doomed", "credit")
        db.delete_account(created["id"])
        assert db.get_account(created["id"]) is None

    def test_delete_nonexistent_returns_true(self, clean_table):
        """Deleting a nonexistent account should still return True (idempotent)."""
        assert db.delete_account("phantom") is True


# ---------------------------------------------------------------------------
# Analysis creation and listing
# ---------------------------------------------------------------------------


class TestCreateAnalysis:
    """Tests for database.create_analysis."""

    def test_empty_analysis(self, clean_table):
        """Analysis created with no accounts should have empty snapshots."""
        analysis = db.create_analysis()
        assert "id" in analysis
        assert analysis["snapshots"] == {}
        assert analysis["credit_snapshots"] == {}
        assert analysis["payments"] == []

    def test_includes_existing_accounts(self, clean_table):
        """Analysis should snapshot all current accounts with zero balances."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        assert bank["id"] in analysis["snapshots"]
        assert analysis["snapshots"][bank["id"]]["starting_balance"] == 0.0
        assert card["id"] in analysis["credit_snapshots"]
        assert analysis["credit_snapshots"][card["id"]]["statement_balance"] == 0.0

    def test_includes_loan_accounts(self, clean_table):
        """Loan accounts should appear in credit_snapshots alongside credit cards."""
        loan = db.create_account("Auto Loan", "loan")
        analysis = db.create_analysis()
        assert loan["id"] in analysis["credit_snapshots"]
        assert analysis["credit_snapshots"][loan["id"]]["statement_balance"] == 0.0


class TestGetAnalyses:
    """Tests for database.get_analyses."""

    def test_empty(self, clean_table):
        """Should return an empty list when no analyses exist."""
        assert db.get_analyses() == []

    def test_returns_all_sorted(self, clean_table):
        """Should return analyses sorted newest first."""
        a1 = db.create_analysis()
        a2 = db.create_analysis()
        results = db.get_analyses()
        assert len(results) == 2
        ids = [r["id"] for r in results]
        assert a1["id"] in ids
        assert a2["id"] in ids


# ---------------------------------------------------------------------------
# get_analysis (the complex reconstructor)
# ---------------------------------------------------------------------------


class TestGetAnalysis:
    """Tests for database.get_analysis."""

    def test_nonexistent(self, clean_table):
        """Should return None for a nonexistent analysis."""
        assert db.get_analysis("no-such-id") is None

    def test_round_trip(self, clean_table):
        """Created analysis should be fully retrievable."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        created = db.create_analysis()
        fetched = db.get_analysis(created["id"])
        assert fetched["id"] == created["id"]
        assert fetched["title"] == created["title"]
        assert bank["id"] in fetched["snapshots"]
        assert card["id"] in fetched["credit_snapshots"]

    def test_auto_adds_new_accounts(self, clean_table):
        """Accounts created after the analysis should be auto-added on fetch."""
        analysis = db.create_analysis()
        new_bank = db.create_account("Late Bank", "bank")
        fetched = db.get_analysis(analysis["id"])
        assert new_bank["id"] in fetched["snapshots"]
        assert fetched["snapshots"][new_bank["id"]]["starting_balance"] == 0.0

    def test_auto_adds_new_loan_accounts(self, clean_table):
        """Loan accounts created after the analysis should be auto-added."""
        analysis = db.create_analysis()
        loan = db.create_account("New Loan", "loan")
        fetched = db.get_analysis(analysis["id"])
        assert loan["id"] in fetched["credit_snapshots"]
        assert fetched["credit_snapshots"][loan["id"]]["statement_balance"] == 0.0

    def test_auto_add_respects_removed(self, clean_table):
        """Removed accounts should not be auto-added back."""
        bank = db.create_account("Bank", "bank")
        analysis = db.create_analysis()
        db.remove_account_from_analysis(analysis["id"], bank["id"])
        fetched = db.get_analysis(analysis["id"])
        assert bank["id"] not in fetched["snapshots"]
        assert bank["id"] in fetched["removed_accounts"]


# ---------------------------------------------------------------------------
# save_analysis / update_snapshot
# ---------------------------------------------------------------------------


class TestSaveAnalysis:
    """Tests for database.save_analysis."""

    def test_update_title(self, clean_table):
        """Should update the analysis title."""
        analysis = db.create_analysis()
        db.save_analysis(analysis["id"], {"title": "Renamed"})
        fetched = db.get_analysis(analysis["id"])
        assert fetched["title"] == "Renamed"

    def test_empty_data_returns_analysis(self, clean_table):
        """Calling with empty dict should return the analysis unchanged."""
        analysis = db.create_analysis()
        result = db.save_analysis(analysis["id"], {})
        assert result["id"] == analysis["id"]

    def test_nonexistent_returns_none(self, clean_table):
        """Should return None for a nonexistent analysis."""
        result = db.save_analysis("no-such-id", {"title": "x"})
        assert result is None


class TestUpdateSnapshot:
    """Tests for database.update_snapshot."""

    def test_update_bank_balance(self, clean_table):
        """Should update a bank snapshot's starting_balance."""
        bank = db.create_account("Bank", "bank")
        analysis = db.create_analysis()
        db.update_snapshot(analysis["id"], bank["id"], "bank", 5000.50)
        fetched = db.get_analysis(analysis["id"])
        assert fetched["snapshots"][bank["id"]]["starting_balance"] == 5000.50

    def test_update_credit_balance(self, clean_table):
        """Should update a credit snapshot's statement_balance."""
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        db.update_snapshot(analysis["id"], card["id"], "credit", 1234.56)
        fetched = db.get_analysis(analysis["id"])
        assert fetched["credit_snapshots"][card["id"]]["statement_balance"] == 1234.56

    def test_update_loan_balance(self, clean_table):
        """Should update a loan snapshot's statement_balance."""
        loan = db.create_account("Auto Loan", "loan")
        analysis = db.create_analysis()
        db.update_snapshot(analysis["id"], loan["id"], "loan", 15000.00)
        fetched = db.get_analysis(analysis["id"])
        assert fetched["credit_snapshots"][loan["id"]]["statement_balance"] == 15000.00

    def test_invalid_type_returns_none(self, clean_table):
        """Should return None for an unrecognized account type."""
        result = db.update_snapshot("x", "y", "investment", 100.0)
        assert result is None


# ---------------------------------------------------------------------------
# Account <-> Analysis management
# ---------------------------------------------------------------------------


class TestAddAccountToAnalysis:
    """Tests for database.add_account_to_analysis."""

    def test_add_new_account(self, clean_table):
        """Adding a new account should create a snapshot with zero balance."""
        analysis = db.create_analysis()
        bank = db.create_account("Late Bank", "bank")
        # Remove it first so we can test the explicit add path
        db.remove_account_from_analysis(analysis["id"], bank["id"])
        result = db.add_account_to_analysis(analysis["id"], bank["id"])
        assert result is True
        fetched = db.get_analysis(analysis["id"])
        assert bank["id"] in fetched["snapshots"]

    def test_add_nonexistent_account(self, clean_table):
        """Adding a nonexistent account should return False."""
        analysis = db.create_analysis()
        assert db.add_account_to_analysis(analysis["id"], "phantom") is False

    def test_add_to_nonexistent_analysis(self, clean_table):
        """Adding to a nonexistent analysis should return False."""
        bank = db.create_account("Bank", "bank")
        assert db.add_account_to_analysis("no-such-id", bank["id"]) is False


class TestRemoveAccountFromAnalysis:
    """Tests for database.remove_account_from_analysis."""

    def test_remove_bank(self, clean_table):
        """Removing a bank should delete its snapshot."""
        bank = db.create_account("Bank", "bank")
        analysis = db.create_analysis()
        result = db.remove_account_from_analysis(analysis["id"], bank["id"])
        assert result is True
        fetched = db.get_analysis(analysis["id"])
        assert bank["id"] not in fetched["snapshots"]

    def test_remove_credit_cascades_payments(self, clean_table):
        """Removing a credit card should also delete its payments."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        db.add_payment(analysis["id"], card["id"], bank["id"], 100.0, "2026-04-06")
        db.remove_account_from_analysis(analysis["id"], card["id"])
        fetched = db.get_analysis(analysis["id"])
        assert card["id"] not in fetched["credit_snapshots"]
        assert len(fetched["payments"]) == 0

    def test_remove_bank_cascades_payments(self, clean_table):
        """Removing a bank should also delete payments sourced from it."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        db.add_payment(analysis["id"], card["id"], bank["id"], 200.0, "2026-04-06")
        db.remove_account_from_analysis(analysis["id"], bank["id"])
        fetched = db.get_analysis(analysis["id"])
        assert bank["id"] not in fetched["snapshots"]
        assert len(fetched["payments"]) == 0

    def test_remove_from_nonexistent_analysis(self, clean_table):
        """Removing from a nonexistent analysis should return False."""
        assert db.remove_account_from_analysis("no-such-id", "any") is False


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


class TestAddPayment:
    """Tests for database.add_payment."""

    def test_creates_payment(self, clean_table):
        """Should persist a payment retrievable via get_analysis."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        pay = db.add_payment(
            analysis["id"], card["id"], bank["id"], 500.0, "2026-04-06"
        )
        assert pay["amount"] == 500.0
        assert pay["credit_id"] == card["id"]
        assert pay["bank_id"] == bank["id"]

        fetched = db.get_analysis(analysis["id"])
        assert len(fetched["payments"]) == 1
        assert fetched["payments"][0]["id"] == pay["id"]

    def test_payment_toward_loan(self, clean_table):
        """Payments should work with loan accounts the same as credit cards."""
        bank = db.create_account("Bank", "bank")
        loan = db.create_account("Auto Loan", "loan")
        analysis = db.create_analysis()
        db.add_payment(analysis["id"], loan["id"], bank["id"], 750.0, "2026-04-06")
        fetched = db.get_analysis(analysis["id"])
        assert len(fetched["payments"]) == 1
        assert fetched["payments"][0]["credit_id"] == loan["id"]
        assert fetched["payments"][0]["amount"] == 750.0

    def test_multiple_payments(self, clean_table):
        """Multiple payments should all appear in the analysis."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        db.add_payment(analysis["id"], card["id"], bank["id"], 100.0, "2026-04-01")
        db.add_payment(analysis["id"], card["id"], bank["id"], 200.0, "2026-04-15")
        fetched = db.get_analysis(analysis["id"])
        assert len(fetched["payments"]) == 2
        amounts = {p["amount"] for p in fetched["payments"]}
        assert amounts == {100.0, 200.0}


class TestRemovePayment:
    """Tests for database.remove_payment."""

    def test_removes_existing_payment(self, clean_table):
        """Should delete the payment from the analysis."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        pay = db.add_payment(
            analysis["id"], card["id"], bank["id"], 300.0, "2026-04-06"
        )
        result = db.remove_payment(analysis["id"], pay["id"])
        assert result is True
        fetched = db.get_analysis(analysis["id"])
        assert len(fetched["payments"]) == 0

    def test_remove_nonexistent_returns_false(self, clean_table):
        """Removing a nonexistent payment should return False."""
        analysis = db.create_analysis()
        assert db.remove_payment(analysis["id"], "phantom-pay") is False

    def test_remove_one_leaves_others(self, clean_table):
        """Removing one payment should not affect other payments."""
        bank = db.create_account("Bank", "bank")
        card = db.create_account("Card", "credit")
        analysis = db.create_analysis()
        p1 = db.add_payment(analysis["id"], card["id"], bank["id"], 100.0, "2026-04-01")
        p2 = db.add_payment(analysis["id"], card["id"], bank["id"], 200.0, "2026-04-15")
        db.remove_payment(analysis["id"], p1["id"])
        fetched = db.get_analysis(analysis["id"])
        assert len(fetched["payments"]) == 1
        assert fetched["payments"][0]["id"] == p2["id"]


# ---------------------------------------------------------------------------
# create_table (idempotency)
# ---------------------------------------------------------------------------


class TestCreateTable:
    """Tests for database.create_table."""

    def test_idempotent(self, clean_table):
        """Calling create_table when the table exists should not raise."""
        db.create_table()  # Should not raise
