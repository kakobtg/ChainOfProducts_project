"""
app/models.py
Database models for the Application Server
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class CompanyRegistration(BaseModel):
    """Company registration request"""
    company_name: str
    signing_public_key: str
    encryption_public_key: str


class Company(BaseModel):
    """Company stored in database"""
    id: int
    company_name: str
    signing_public_key: str
    encryption_public_key: str
    created_at: datetime


class TransactionCreate(BaseModel):
    """Create transaction request"""
    protected_document: Dict[str, Any]


class Transaction(BaseModel):
    """Transaction stored in database"""
    id: int
    transaction_id: int
    protected_document: Dict[str, Any]
    seller: Optional[str] = None
    buyer: Optional[str] = None
    created_at: datetime
    buyer_signed: bool = False


class BuyerSignRequest(BaseModel):
    """Buyer signature request"""
    buyer_signature: Dict[str, str]  # Contains company and signature


class ShareRecord(BaseModel):
    """Share record for tracking disclosures"""
    id: int
    transaction_id: int
    shared_by: str
    shared_with: str
    share_type: str  # 'individual' or 'group'
    timestamp: datetime
    signature: str  # Signature of share record by sharer


class ShareCreate(BaseModel):
    """Create share record request"""
    shared_by: str
    shared_with: str
    signature: str  # Signature of share record


class GroupShareCreate(BaseModel):
    """Create group share record request"""
    shared_by: str
    group_id: str
    signature: str


class TransactionResponse(BaseModel):
    """Transaction response"""
    transaction: Transaction
    share_records: List[ShareRecord]