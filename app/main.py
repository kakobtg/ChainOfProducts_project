"""
app/main.py
Application Server (DMZ) - VM2
FastAPI server that never sees plaintext transactions
"""

import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uvicorn

from .models import (
    CompanyRegistration, TransactionCreate, BuyerSignRequest,
    ShareCreate, GroupShareCreate, Transaction, ShareRecord
)
from .db import Database

app = FastAPI(
    title="ChainOfProduct Application Server",
    description="Secure transaction storage in the DMZ",
    version="1.0.0"
)

# CORS middleware (configure appropriately for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL must be set to the Postgres connection string (VM3)")
# Connect to VM3 over the internal network
db = Database(db_url)


@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "service": "ChainOfProduct Application Server",
        "status": "operational",
        "version": "1.0.0"
    }


@app.post("/register_company", status_code=status.HTTP_201_CREATED)
def register_company(registration: CompanyRegistration):
    """
    Register a new company with public keys
    """
    try:
        # Check if company already exists
        existing = db.get_company(registration.company_name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Company {registration.company_name} already registered"
            )
        
        # Register company
        company_id = db.register_company(
            registration.company_name,
            registration.signing_public_key,
            registration.encryption_public_key
        )
        
        return {
            "id": company_id,
            "company_name": registration.company_name,
            "message": "Company registered successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@app.get("/companies")
def list_companies():
    """List all registered companies"""
    try:
        companies = db.list_companies()
        return {"companies": companies}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list companies: {str(e)}"
        )


@app.get("/companies/{company_name}")
def get_company(company_name: str):
    """Get company public keys"""
    try:
        company = db.get_company(company_name)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company {company_name} not found"
            )
        return company
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company: {str(e)}"
        )


@app.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(transaction: TransactionCreate):
    """
    Store a protected transaction
    Server never sees plaintext - only encrypted data
    """
    try:
        protected_doc = transaction.protected_document
        
        # Extract metadata from protected document
        transaction_id = protected_doc.get("transaction_id")
        if not transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Protected document missing transaction_id"
            )
        
        # Extract seller and buyer from signatures
        seller = protected_doc.get("signatures", {}).get("seller", {}).get("company")
        buyer_sig = protected_doc.get("signatures", {}).get("buyer")
        buyer = buyer_sig.get("company") if buyer_sig else None
        
        # Check if transaction already exists
        existing = db.get_transaction(transaction_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transaction {transaction_id} already exists"
            )
        
        # Store transaction
        db_id = db.create_transaction(transaction_id, protected_doc, seller, buyer)
        
        return {
            "id": db_id,
            "transaction_id": transaction_id,
            "message": "Transaction stored successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store transaction: {str(e)}"
        )


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int):
    """
    Retrieve a protected transaction
    Returns encrypted data only
    """
    try:
        transaction = db.get_transaction(transaction_id)
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {transaction_id} not found"
            )
        
        # Get share records
        share_records = db.get_share_records(transaction_id)
        group_share_records = db.get_group_share_records(transaction_id)
        
        return {
            "transaction": transaction,
            "share_records": share_records,
            "group_share_records": group_share_records
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve transaction: {str(e)}"
        )


@app.post("/transactions/{transaction_id}/buyer_sign")
def buyer_sign_transaction(transaction_id: int, request: BuyerSignRequest):
    """
    Add buyer signature to a transaction
    """
    try:
        # Get existing transaction
        transaction = db.get_transaction(transaction_id)
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {transaction_id} not found"
            )
        
        # Check if already signed
        if transaction.get("buyer_signed"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transaction already signed by buyer"
            )
        
        # Update protected document with buyer signature
        protected_doc = transaction["protected_document"]
        protected_doc["signatures"]["buyer"] = request.buyer_signature
        
        # Update in database
        success = db.update_transaction_buyer_signature(transaction_id, protected_doc)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update transaction"
            )
        
        return {
            "transaction_id": transaction_id,
            "message": "Buyer signature added successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add buyer signature: {str(e)}"
        )


@app.post("/transactions/{transaction_id}/share")
def share_transaction(transaction_id: int, share: ShareCreate):
    """
    Record that a transaction was shared with someone
    Creates an auditable share record (SR4: Integrity 2)
    """
    try:
        # Verify transaction exists
        transaction = db.get_transaction(transaction_id)
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {transaction_id} not found"
            )
        
        # Create share record
        record_id = db.create_share_record(
            transaction_id,
            share.shared_by,
            share.shared_with,
            share.signature
        )
        
        return {
            "id": record_id,
            "transaction_id": transaction_id,
            "shared_by": share.shared_by,
            "shared_with": share.shared_with,
            "message": "Share record created"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create share record: {str(e)}"
        )


@app.post("/transactions/{transaction_id}/share_group")
def share_transaction_group(transaction_id: int, share: GroupShareCreate):
    """
    Record that a transaction was shared with a group
    """
    try:
        # Verify transaction exists
        transaction = db.get_transaction(transaction_id)
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {transaction_id} not found"
            )
        
        # Create group share record
        record_id = db.create_group_share_record(
            transaction_id,
            share.shared_by,
            share.group_id,
            share.signature
        )
        
        return {
            "id": record_id,
            "transaction_id": transaction_id,
            "shared_by": share.shared_by,
            "group_id": share.group_id,
            "message": "Group share record created"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create group share record: {str(e)}"
        )


@app.get("/transactions/{transaction_id}/shares")
def get_shares(transaction_id: int):
    """
    Get all share records for a transaction
    Allows seller to verify who buyer shared with (SR4)
    """
    try:
        records = db.get_share_records(transaction_id)
        return {"share_records": records}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get share records: {str(e)}"
        )


@app.get("/transactions/{transaction_id}/group_shares")
def get_group_shares(transaction_id: int):
    """
    Get all group share records for a transaction
    """
    try:
        records = db.get_group_share_records(transaction_id)
        return {"group_share_records": records}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get group share records: {str(e)}"
        )


def start_server(host: str = "0.0.0.0", port: int = 8001):
    """Start the application server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
