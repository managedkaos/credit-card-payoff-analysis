import datetime
import uuid
import os
import boto3
from decimal import Decimal
from typing import Any, Dict

# Environment setup
DYNAMODB_ENDPOINT_URL = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNTS_TABLE_NAME = os.environ.get("ACCOUNTS_TABLE_NAME", "cc_payoff_accounts")
ANALYSES_TABLE_NAME = os.environ.get("ANALYSES_TABLE_NAME", "cc_payoff_analyses")

# Set dummy credentials if endpoint is localhost
if "localhost" in DYNAMODB_ENDPOINT_URL:
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "dummy")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "dummy")

def get_dynamodb():
    if DYNAMODB_ENDPOINT_URL:
        kwargs = {
            "region_name": AWS_REGION,
            "endpoint_url": DYNAMODB_ENDPOINT_URL
        }
        if "localhost" in DYNAMODB_ENDPOINT_URL:
            kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "dummy")
            kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "dummy")
        return boto3.resource("dynamodb", **kwargs)
    return boto3.resource("dynamodb", region_name=AWS_REGION)

dynamodb = get_dynamodb()

def init_db():
    """Create tables if they don't exist yet."""
    try:
        table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
        table.load()
    except Exception:
        dynamodb.create_table(
            TableName=ACCOUNTS_TABLE_NAME,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )
    
    try:
        table = dynamodb.Table(ANALYSES_TABLE_NAME)
        table.load()
    except Exception:
        dynamodb.create_table(
            TableName=ANALYSES_TABLE_NAME,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

def replace_decimals(obj):
    """Convert DynamoDB Decimal to native float/int."""
    if isinstance(obj, list):
        return [replace_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: replace_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj

def float_to_decimal(obj):
    """Convert float to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: float_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [float_to_decimal(i) for i in obj]
    return obj

def create_account(name: str, acc_type: str) -> dict:
    acc_id = str(uuid.uuid4())
    account = {
        "id": acc_id,
        "name": name,
        "type": acc_type,  
    }
    table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    table.put_item(Item=account)
    return account

def get_accounts():
    table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    response = table.scan()
    accounts = response.get('Items', [])
    return replace_decimals(accounts)

def get_account(acc_id: str):
    table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    response = table.get_item(Key={'id': acc_id})
    return replace_decimals(response.get('Item'))

def update_account(acc_id: str, name: str):
    table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        response = table.update_item(
            Key={'id': acc_id},
            UpdateExpression="set #name = :n",
            ExpressionAttributeNames={'#name': 'name'},
            ExpressionAttributeValues={':n': name},
            ReturnValues="ALL_NEW"
        )
        return replace_decimals(response.get('Attributes'))
    except Exception:
        return None

def delete_account(acc_id: str):
    table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    table.delete_item(Key={'id': acc_id})
    return True

def create_analysis() -> dict:
    analysis_id = str(uuid.uuid4())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    bank_snaps = {}
    credit_snaps = {}

    for acc in get_accounts():
        if acc["type"] == "bank":
            bank_snaps[acc["id"]] = {"name": acc["name"], "starting_balance": 0.0}
        elif acc["type"] == "credit":
            credit_snaps[acc["id"]] = {"name": acc["name"], "statement_balance": 0.0}

    analysis = {
        "id": analysis_id,
        "title": f"Analysis {now}",
        "date": datetime.date.today().isoformat(),
        "snapshots": bank_snaps,
        "credit_snapshots": credit_snaps,
        "removed_accounts": [],
        "payments": [],
    }
    
    table = dynamodb.Table(ANALYSES_TABLE_NAME)
    table.put_item(Item=float_to_decimal(analysis))
    return analysis

def get_analyses():
    table = dynamodb.Table(ANALYSES_TABLE_NAME)
    response = table.scan()
    analyses = replace_decimals(response.get('Items', []))
    return sorted(analyses, key=lambda x: x["date"], reverse=True)

def get_analysis_fetch(analysis_id: str):
    # Base fetch without recursive saving to prevent infinite loop
    table = dynamodb.Table(ANALYSES_TABLE_NAME)
    response = table.get_item(Key={'id': analysis_id})
    return replace_decimals(response.get('Item'))

def get_analysis(analysis_id: str):
    analysis = get_analysis_fetch(analysis_id)
    if not analysis:
        return None
        
    removed = analysis.get("removed_accounts", [])
    changed = False
    
    for acc in get_accounts():
        acc_id = acc["id"]
        if acc_id in removed:
            continue
            
        if acc["type"] == "bank" and acc_id not in analysis.get("snapshots", {}):
            analysis.setdefault("snapshots", {})[acc_id] = {"name": acc["name"], "starting_balance": 0.0}
            changed = True
        elif acc["type"] == "credit" and acc_id not in analysis.get("credit_snapshots", {}):
            analysis.setdefault("credit_snapshots", {})[acc_id] = {"name": acc["name"], "statement_balance": 0.0}
            changed = True
            
    if changed:
        table = dynamodb.Table(ANALYSES_TABLE_NAME)
        table.put_item(Item=float_to_decimal(analysis))
        
    return analysis

def save_analysis(analysis_id: str, data: dict):
    analysis = get_analysis_fetch(analysis_id)
    if not analysis:
        return None
    
    analysis.update(data)
    
    table = dynamodb.Table(ANALYSES_TABLE_NAME)
    table.put_item(Item=float_to_decimal(analysis))
    return analysis

def add_account_to_analysis(analysis_id: str, acc_id: str):
    analysis = get_analysis_fetch(analysis_id)
    acc = get_account(acc_id)
    if not analysis or not acc:
        return False
        
    if "removed_accounts" in analysis and acc_id in analysis["removed_accounts"]:
        analysis["removed_accounts"].remove(acc_id)
    
    if acc["type"] == "bank" and acc_id not in analysis.setdefault("snapshots", {}):
        analysis["snapshots"][acc_id] = {"name": acc["name"], "starting_balance": 0.0}
    elif acc["type"] == "credit" and acc_id not in analysis.setdefault("credit_snapshots", {}):
        analysis["credit_snapshots"][acc_id] = {"name": acc["name"], "statement_balance": 0.0}
        
    save_analysis(analysis_id, analysis)
    return True

def remove_account_from_analysis(analysis_id: str, acc_id: str):
    analysis = get_analysis_fetch(analysis_id)
    if not analysis:
        return False
    
    removed = False
    
    analysis.setdefault("removed_accounts", [])
    if acc_id not in analysis["removed_accounts"]:
        analysis["removed_accounts"].append(acc_id)
        
    if acc_id in analysis.get("snapshots", {}):
        del analysis["snapshots"][acc_id]
        analysis["payments"] = [p for p in analysis.get("payments", []) if p["bank_id"] != acc_id]
        removed = True
        
    if acc_id in analysis.get("credit_snapshots", {}):
        del analysis["credit_snapshots"][acc_id]
        analysis["payments"] = [p for p in analysis.get("payments", []) if p["credit_id"] != acc_id]
        removed = True

    if removed:
        save_analysis(analysis_id, analysis)

    return removed

def add_payment(analysis_id: str, credit_id: str, bank_id: str, amount: float, p_date: str):
    analysis = get_analysis_fetch(analysis_id)
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
    analysis.setdefault("payments", []).append(payment)
    save_analysis(analysis_id, analysis)
    return payment

def remove_payment(analysis_id: str, payment_id: str):
    analysis = get_analysis_fetch(analysis_id)
    if not analysis:
        return False
    analysis["payments"] = [p for p in analysis.get("payments", []) if p["id"] != payment_id]
    save_analysis(analysis_id, analysis)
    return True
