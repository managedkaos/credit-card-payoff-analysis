from typing import Dict, List, Literal

from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    type: Literal["bank", "credit"]


class PaymentInfo(BaseModel):
    id: str
    credit_id: str
    bank_id: str
    amount: float
    date: str


class BankSnapshot(BaseModel):
    name: str
    starting_balance: float


class CreditSnapshot(BaseModel):
    name: str
    statement_balance: float


class AnalysisData(BaseModel):
    id: str
    title: str
    date: str
    snapshots: Dict[str, BankSnapshot] = {}
    credit_snapshots: Dict[str, CreditSnapshot] = {}
    payments: List[PaymentInfo] = []
