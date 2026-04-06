import datetime
import uuid
from typing import Any, Dict

# In-memory store
ACCOUNTS: Dict[str, Dict[str, Any]] = {}
ANALYSES: Dict[str, Dict[str, Any]] = {}


def create_account(name: str, acc_type: str) -> dict:
    acc_id = str(uuid.uuid4())
    ACCOUNTS[acc_id] = {
        "id": acc_id,
        "name": name,
        "type": acc_type,  # 'bank' or 'credit'
    }
    return ACCOUNTS[acc_id]


def get_accounts():
    return list(ACCOUNTS.values())


def get_account(acc_id: str):
    return ACCOUNTS.get(acc_id)


def update_account(acc_id: str, name: str):
    if acc_id in ACCOUNTS:
        ACCOUNTS[acc_id]["name"] = name
        return ACCOUNTS[acc_id]
    return None


def create_analysis() -> dict:
    """Creates a new empty analysis snapshot."""
    analysis_id = str(uuid.uuid4())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Initialize snapshots from current accounts
    bank_snaps = {}
    credit_snaps = {}

    for acc in get_accounts():
        if acc["type"] == "bank":
            bank_snaps[acc["id"]] = {"name": acc["name"], "starting_balance": 0.0}
        elif acc["type"] == "credit":
            credit_snaps[acc["id"]] = {"name": acc["name"], "statement_balance": 0.0}

    ANALYSES[analysis_id] = {
        "id": analysis_id,
        "title": f"Analysis {now}",
        "date": datetime.date.today().isoformat(),
        "snapshots": bank_snaps,
        "credit_snapshots": credit_snaps,
        "removed_accounts": [],
        "payments": [],  # list of dicts: {"id", "credit_id", "bank_id", "amount", "date"}
    }
    return ANALYSES[analysis_id]


def get_analyses():
    # Return sorted by newest
    return sorted(list(ANALYSES.values()), key=lambda x: x["date"], reverse=True)


def get_analysis(analysis_id: str):
    analysis = ANALYSES.get(analysis_id)
    if not analysis:
        return None

    removed = analysis.get("removed_accounts", [])

    for acc in get_accounts():
        acc_id = acc["id"]
        if acc_id in removed:
            continue

        if acc["type"] == "bank" and acc_id not in analysis.get("snapshots", {}):
            analysis["snapshots"][acc_id] = {
                "name": acc["name"],
                "starting_balance": 0.0,
            }
        elif acc["type"] == "credit" and acc_id not in analysis.get(
            "credit_snapshots", {}
        ):
            analysis["credit_snapshots"][acc_id] = {
                "name": acc["name"],
                "statement_balance": 0.0,
            }

    return analysis


def save_analysis(analysis_id: str, data: dict):
    if analysis_id in ANALYSES:
        ANALYSES[analysis_id].update(data)
        return ANALYSES[analysis_id]
    return None


def delete_account(acc_id: str):
    if acc_id in ACCOUNTS:
        del ACCOUNTS[acc_id]
        return True
    return False


def add_account_to_analysis(analysis_id: str, acc_id: str):
    analysis = get_analysis(analysis_id)
    acc = get_account(acc_id)
    if not analysis or not acc:
        return False

    if "removed_accounts" in analysis and acc_id in analysis["removed_accounts"]:
        analysis["removed_accounts"].remove(acc_id)

    if acc["type"] == "bank" and acc_id not in analysis["snapshots"]:
        analysis["snapshots"][acc_id] = {"name": acc["name"], "starting_balance": 0.0}
    elif acc["type"] == "credit" and acc_id not in analysis["credit_snapshots"]:
        analysis["credit_snapshots"][acc_id] = {
            "name": acc["name"],
            "statement_balance": 0.0,
        }
    return True


def remove_account_from_analysis(analysis_id: str, acc_id: str):
    analysis = get_analysis(analysis_id)
    if not analysis:
        return False

    removed = False

    if "removed_accounts" not in analysis:
        analysis["removed_accounts"] = []
    if acc_id not in analysis["removed_accounts"]:
        analysis["removed_accounts"].append(acc_id)

    if acc_id in analysis.get("snapshots", {}):
        del analysis["snapshots"][acc_id]
        analysis["payments"] = [
            p for p in analysis["payments"] if p["bank_id"] != acc_id
        ]
        removed = True

    if acc_id in analysis.get("credit_snapshots", {}):
        del analysis["credit_snapshots"][acc_id]
        analysis["payments"] = [
            p for p in analysis["payments"] if p["credit_id"] != acc_id
        ]
        removed = True

    return removed


def add_payment(
    analysis_id: str, credit_id: str, bank_id: str, amount: float, p_date: str
):
    analysis = get_analysis(analysis_id)
    if not analysis:
        return None
    payment_id = str(uuid.uuid4())
    payment = {
        "id": payment_id,
        "credit_id": credit_id,
        "bank_id": bank_id,
        "amount": amount,
        "date": p_date,
    }
    analysis["payments"].append(payment)
    return payment


def remove_payment(analysis_id: str, payment_id: str):
    analysis = get_analysis(analysis_id)
    if not analysis:
        return False
    analysis["payments"] = [p for p in analysis["payments"] if p["id"] != payment_id]
    return True
