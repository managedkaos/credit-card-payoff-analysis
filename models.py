"""Pydantic models for request validation and data serialization."""

from typing import Dict, List, Literal

from pydantic import BaseModel


class AccountCreate(BaseModel):
    """Input model for creating a bank or credit account."""

    name: str
    type: Literal["bank", "credit", "loan"]


class PaymentInfo(BaseModel):
    """A single payment linking a bank account to a credit card."""

    id: str
    credit_id: str
    bank_id: str
    amount: float
    date: str


class BankSnapshot(BaseModel):
    """Point-in-time snapshot of a bank account's starting balance."""

    name: str
    starting_balance: float


class CreditSnapshot(BaseModel):
    """Point-in-time snapshot of a credit card's statement balance."""

    name: str
    statement_balance: float


class AnalysisData(BaseModel):
    """Full analysis containing bank/credit snapshots and payment records."""

    id: str
    title: str
    date: str
    snapshots: Dict[str, BankSnapshot] = {}
    credit_snapshots: Dict[str, CreditSnapshot] = {}
    payments: List[PaymentInfo] = []
