import datetime
import os
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key

_table = None


def _get_table():
    global _table
    if _table is None:
        endpoint = os.environ.get("DYNAMODB_ENDPOINT")
        table_name = os.environ.get("DYNAMODB_TABLE", "CreditCardPayoff")
        kwargs = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        dynamodb = boto3.resource("dynamodb", **kwargs)
        _table = dynamodb.Table(table_name)
    return _table


def create_table():
    """Create the DynamoDB table if it does not exist. Idempotent."""
    endpoint = os.environ.get("DYNAMODB_ENDPOINT")
    table_name = os.environ.get("DYNAMODB_TABLE", "CreditCardPayoff")
    kwargs = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    client = boto3.client("dynamodb", **kwargs)
    try:
        client.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=table_name)
    except client.exceptions.ResourceInUseException:
        pass


def _decimal_to_float(obj):
    """Recursively convert Decimal values to float."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def create_account(name: str, acc_type: str) -> dict:
    acc_id = str(uuid.uuid4())
    table = _get_table()
    table.put_item(
        Item={
            "PK": f"ACCOUNT#{acc_id}",
            "SK": f"ACCOUNT#{acc_id}",
            "name": name,
            "type": acc_type,
        }
    )
    return {"id": acc_id, "name": name, "type": acc_type}


def get_accounts() -> list:
    table = _get_table()
    response = table.scan(
        FilterExpression=Attr("PK").begins_with("ACCOUNT#")
        & Attr("SK").begins_with("ACCOUNT#")
    )
    items = response.get("Items", [])
    return [
        {
            "id": item["PK"].replace("ACCOUNT#", ""),
            "name": item["name"],
            "type": item["type"],
        }
        for item in items
    ]


def get_account(acc_id: str):
    table = _get_table()
    response = table.get_item(
        Key={"PK": f"ACCOUNT#{acc_id}", "SK": f"ACCOUNT#{acc_id}"}
    )
    item = response.get("Item")
    if not item:
        return None
    return {"id": acc_id, "name": item["name"], "type": item["type"]}


def update_account(acc_id: str, name: str):
    table = _get_table()
    try:
        table.update_item(
            Key={"PK": f"ACCOUNT#{acc_id}", "SK": f"ACCOUNT#{acc_id}"},
            UpdateExpression="SET #n = :name",
            ExpressionAttributeNames={"#n": "name"},
            ExpressionAttributeValues={":name": name},
            ConditionExpression=Attr("PK").exists(),
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None
    return {"id": acc_id, "name": name}


def delete_account(acc_id: str):
    table = _get_table()
    table.delete_item(Key={"PK": f"ACCOUNT#{acc_id}", "SK": f"ACCOUNT#{acc_id}"})
    return True


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


def create_analysis() -> dict:
    """Create a new analysis snapshot with all current accounts."""
    analysis_id = str(uuid.uuid4())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.date.today().isoformat()

    accounts = get_accounts()
    table = _get_table()

    with table.batch_writer() as batch:
        # META item
        batch.put_item(
            Item={
                "PK": f"ANALYSIS#{analysis_id}",
                "SK": "META",
                "title": f"Analysis {now}",
                "date": today,
                "removed_accounts": [],
            }
        )
        # Snapshot items for each account
        for acc in accounts:
            if acc["type"] == "bank":
                batch.put_item(
                    Item={
                        "PK": f"ANALYSIS#{analysis_id}",
                        "SK": f"BANK#{acc['id']}",
                        "account_name": acc["name"],
                        "starting_balance": Decimal("0"),
                    }
                )
            elif acc["type"] == "credit":
                batch.put_item(
                    Item={
                        "PK": f"ANALYSIS#{analysis_id}",
                        "SK": f"CREDIT#{acc['id']}",
                        "account_name": acc["name"],
                        "statement_balance": Decimal("0"),
                    }
                )

    # Return the same shape the caller expects
    bank_snaps = {}
    credit_snaps = {}
    for acc in accounts:
        if acc["type"] == "bank":
            bank_snaps[acc["id"]] = {"name": acc["name"], "starting_balance": 0.0}
        elif acc["type"] == "credit":
            credit_snaps[acc["id"]] = {"name": acc["name"], "statement_balance": 0.0}

    return {
        "id": analysis_id,
        "title": f"Analysis {now}",
        "date": today,
        "snapshots": bank_snaps,
        "credit_snapshots": credit_snaps,
        "removed_accounts": [],
        "payments": [],
    }


def get_analyses() -> list:
    """Return list of analyses (id, title, date) sorted newest first."""
    table = _get_table()
    response = table.scan(
        FilterExpression=Attr("SK").eq("META") & Attr("PK").begins_with("ANALYSIS#")
    )
    items = response.get("Items", [])
    results = [
        {
            "id": item["PK"].replace("ANALYSIS#", ""),
            "title": item.get("title", ""),
            "date": item.get("date", ""),
        }
        for item in items
    ]
    return sorted(results, key=lambda x: x["date"], reverse=True)


def get_analysis(analysis_id: str):
    """Fetch a full analysis by querying all items under its partition key."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"ANALYSIS#{analysis_id}")
    )
    items = response.get("Items", [])
    if not items:
        return None

    meta = None
    snapshots = {}
    credit_snapshots = {}
    payments = []

    for item in items:
        sk = item["SK"]

        if sk == "META":
            meta = item
        elif "#PAY#" in sk:
            # Payment: SK = CREDIT#<credit_id>#PAY#<pay_id>
            parts = sk.split("#PAY#")
            credit_id = parts[0].replace("CREDIT#", "")
            pay_id = parts[1]
            payments.append(
                {
                    "id": pay_id,
                    "credit_id": credit_id,
                    "bank_id": item.get("source_bank_id", ""),
                    "amount": float(item.get("payment_amount", 0)),
                    "date": item.get("date", ""),
                }
            )
        elif sk.startswith("BANK#"):
            acc_id = sk.replace("BANK#", "")
            snapshots[acc_id] = {
                "name": item.get("account_name", ""),
                "starting_balance": float(item.get("starting_balance", 0)),
            }
        elif sk.startswith("CREDIT#"):
            acc_id = sk.replace("CREDIT#", "")
            credit_snapshots[acc_id] = {
                "name": item.get("account_name", ""),
                "statement_balance": float(item.get("statement_balance", 0)),
            }

    if meta is None:
        return None

    removed = list(meta.get("removed_accounts", []))

    # Auto-add accounts created after this analysis
    current_accounts = get_accounts()
    for acc in current_accounts:
        acc_id = acc["id"]
        if acc_id in removed:
            continue
        if acc["type"] == "bank" and acc_id not in snapshots:
            # Write new snapshot to DynamoDB
            table.put_item(
                Item={
                    "PK": f"ANALYSIS#{analysis_id}",
                    "SK": f"BANK#{acc_id}",
                    "account_name": acc["name"],
                    "starting_balance": Decimal("0"),
                }
            )
            snapshots[acc_id] = {"name": acc["name"], "starting_balance": 0.0}
        elif acc["type"] == "credit" and acc_id not in credit_snapshots:
            table.put_item(
                Item={
                    "PK": f"ANALYSIS#{analysis_id}",
                    "SK": f"CREDIT#{acc_id}",
                    "account_name": acc["name"],
                    "statement_balance": Decimal("0"),
                }
            )
            credit_snapshots[acc_id] = {
                "name": acc["name"],
                "statement_balance": 0.0,
            }

    return _decimal_to_float(
        {
            "id": analysis_id,
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "snapshots": snapshots,
            "credit_snapshots": credit_snapshots,
            "removed_accounts": removed,
            "payments": payments,
        }
    )


def save_analysis(analysis_id: str, data: dict):
    """Update META-level fields on an analysis (title, date)."""
    if not data:
        return get_analysis(analysis_id)

    table = _get_table()
    expr_parts = []
    attr_names = {}
    attr_values = {}

    for i, (key, val) in enumerate(data.items()):
        placeholder_name = f"#k{i}"
        placeholder_val = f":v{i}"
        expr_parts.append(f"{placeholder_name} = {placeholder_val}")
        attr_names[placeholder_name] = key
        attr_values[placeholder_val] = val

    try:
        table.update_item(
            Key={"PK": f"ANALYSIS#{analysis_id}", "SK": "META"},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
            ConditionExpression=Attr("PK").exists(),
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None

    return get_analysis(analysis_id)


def update_snapshot(analysis_id: str, account_id: str, acc_type: str, amount: float):
    """Update starting_balance (bank) or statement_balance (credit) on a snapshot."""
    table = _get_table()

    if acc_type == "bank":
        sk = f"BANK#{account_id}"
        field = "starting_balance"
    elif acc_type == "credit":
        sk = f"CREDIT#{account_id}"
        field = "statement_balance"
    else:
        return None

    table.update_item(
        Key={"PK": f"ANALYSIS#{analysis_id}", "SK": sk},
        UpdateExpression="SET #f = :val",
        ExpressionAttributeNames={"#f": field},
        ExpressionAttributeValues={":val": Decimal(str(amount))},
    )
    return True


# ---------------------------------------------------------------------------
# Account <-> Analysis management
# ---------------------------------------------------------------------------


def add_account_to_analysis(analysis_id: str, acc_id: str):
    acc = get_account(acc_id)
    if not acc:
        return False

    table = _get_table()

    # Remove from removed_accounts list on META
    meta_response = table.get_item(Key={"PK": f"ANALYSIS#{analysis_id}", "SK": "META"})
    meta = meta_response.get("Item")
    if not meta:
        return False

    removed = list(meta.get("removed_accounts", []))
    if acc_id in removed:
        removed.remove(acc_id)
        table.update_item(
            Key={"PK": f"ANALYSIS#{analysis_id}", "SK": "META"},
            UpdateExpression="SET removed_accounts = :ra",
            ExpressionAttributeValues={":ra": removed},
        )

    # Add snapshot item (won't overwrite if it exists due to condition)
    if acc["type"] == "bank":
        sk = f"BANK#{acc_id}"
        item = {
            "PK": f"ANALYSIS#{analysis_id}",
            "SK": sk,
            "account_name": acc["name"],
            "starting_balance": Decimal("0"),
        }
    elif acc["type"] == "credit":
        sk = f"CREDIT#{acc_id}"
        item = {
            "PK": f"ANALYSIS#{analysis_id}",
            "SK": sk,
            "account_name": acc["name"],
            "statement_balance": Decimal("0"),
        }
    else:
        return False

    try:
        table.put_item(
            Item=item,
            ConditionExpression=Attr("PK").not_exists(),
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        pass  # Snapshot already exists, that's fine

    return True


def remove_account_from_analysis(analysis_id: str, acc_id: str):
    table = _get_table()

    # Add to removed_accounts on META
    meta_response = table.get_item(Key={"PK": f"ANALYSIS#{analysis_id}", "SK": "META"})
    meta = meta_response.get("Item")
    if not meta:
        return False

    removed = list(meta.get("removed_accounts", []))
    if acc_id not in removed:
        removed.append(acc_id)
        table.update_item(
            Key={"PK": f"ANALYSIS#{analysis_id}", "SK": "META"},
            UpdateExpression="SET removed_accounts = :ra",
            ExpressionAttributeValues={":ra": removed},
        )

    did_remove = False
    pk = f"ANALYSIS#{analysis_id}"

    # Try deleting bank snapshot
    try:
        table.delete_item(
            Key={"PK": pk, "SK": f"BANK#{acc_id}"},
            ConditionExpression=Attr("PK").exists(),
        )
        did_remove = True
        # Delete payments that reference this bank
        _delete_payments_by_bank(analysis_id, acc_id)
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        pass

    # Try deleting credit snapshot and its payments
    try:
        table.delete_item(
            Key={"PK": pk, "SK": f"CREDIT#{acc_id}"},
            ConditionExpression=Attr("PK").exists(),
        )
        did_remove = True
        # Delete all payments under this credit card
        _delete_payments_by_credit(analysis_id, acc_id)
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        pass

    return did_remove


def _delete_payments_by_credit(analysis_id: str, credit_id: str):
    """Delete all payment items for a specific credit card in an analysis."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"ANALYSIS#{analysis_id}")
        & Key("SK").begins_with(f"CREDIT#{credit_id}#PAY#")
    )
    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})


def _delete_payments_by_bank(analysis_id: str, bank_id: str):
    """Delete all payment items that reference a specific bank account."""
    table = _get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"ANALYSIS#{analysis_id}"),
        FilterExpression=Attr("source_bank_id").eq(bank_id),
    )
    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            if "#PAY#" in item["SK"]:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def add_payment(
    analysis_id: str, credit_id: str, bank_id: str, amount: float, p_date: str
):
    table = _get_table()
    payment_id = str(uuid.uuid4())
    table.put_item(
        Item={
            "PK": f"ANALYSIS#{analysis_id}",
            "SK": f"CREDIT#{credit_id}#PAY#{payment_id}",
            "payment_amount": Decimal(str(amount)),
            "source_bank_id": bank_id,
            "date": p_date,
        }
    )
    return {
        "id": payment_id,
        "credit_id": credit_id,
        "bank_id": bank_id,
        "amount": amount,
        "date": p_date,
    }


def remove_payment(analysis_id: str, payment_id: str):
    """Remove a payment by ID. Queries all items under the analysis PK and finds the matching payment SK in Python."""
    table = _get_table()
    pay_suffix = f"#PAY#{payment_id}"
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"ANALYSIS#{analysis_id}")
    )
    for item in response.get("Items", []):
        if item["SK"].endswith(pay_suffix):
            table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
            return True
    return False
