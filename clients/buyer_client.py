"""
clients/buyer_client.py
Buyer client for signing and sharing transactions
"""

import sys
import json
import base64
import requests
import os
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from chainofproduct.library import buyer_sign, unprotect, check
from chainofproduct.keymanager import KeyManager, PublicKeyStore
from chainofproduct import crypto


class BuyerClient:
    """Client for buyer operations"""
    
    def __init__(self, buyer_name: str, app_server_url: Optional[str] = None):
        self.buyer_name = buyer_name
        self.app_server_url = app_server_url or os.getenv("APP_SERVER_URL", "http://localhost:8001")
        self.key_manager = KeyManager()
        self.public_key_store = PublicKeyStore()
    
    def register(self):
        """Register buyer with application server"""
        print(f"Registering buyer: {self.buyer_name}")
        
        # Generate keys if not exist
        try:
            public_keys = self.key_manager.export_public_keys(self.buyer_name)
        except FileNotFoundError:
            print(f"  Generating new keys for {self.buyer_name}...")
            public_keys = self.key_manager.generate_company_keys(self.buyer_name)
        
        # Register with server
        response = requests.post(
            f"{self.app_server_url}/register_company",
            json=public_keys
        )
        
        if response.status_code == 201:
            print(f"✓ Buyer registered successfully")
            return True
        elif response.status_code == 409:
            print(f"✓ Buyer already registered")
            return True
        else:
            print(f"✗ Registration failed: {response.text}")
            return False
    
    def sign_transaction(self, transaction_id: int):
        """
        Retrieve, verify, and sign a transaction
        """
        print(f"\n=== Signing Transaction {transaction_id} ===")
        
        # Retrieve transaction
        print(f"Retrieving transaction from server...")
        response = requests.get(f"{self.app_server_url}/transactions/{transaction_id}")
        
        if response.status_code != 200:
            print(f"✗ Failed to retrieve transaction: {response.text}")
            return None
        
        data = response.json()
        protected_doc = data["transaction"]["protected_document"]
        
        # Verify transaction
        print(f"Verifying transaction integrity...")
        verification = check(protected_doc, self.public_key_store)
        
        if not verification["valid"]:
            print(f"✗ Transaction verification failed!")
            for error in verification["errors"]:
                print(f"  - {error}")
            return None
        
        print(f"✓ Transaction verified")
        
        # Decrypt to review (buyer should review before signing)
        print(f"Decrypting transaction for review...")
        try:
            result = unprotect(protected_doc, self.buyer_name, self.key_manager)
            transaction_data = result["transaction"]
            print(f"✓ Transaction decrypted")
            print(f"  Seller: {transaction_data['seller']}")
            print(f"  Buyer: {transaction_data['buyer']}")
            print(f"  Product: {transaction_data['product']}")
            print(f"  Units: {transaction_data['units']}")
            print(f"  Amount: ${transaction_data['amount']:,}")
        except Exception as e:
            print(f"✗ Failed to decrypt: {e}")
            return None
        
        # Sign transaction
        print(f"Adding buyer signature...")
        signed_doc = buyer_sign(protected_doc, self.buyer_name, self.key_manager)
        
        # Upload signature to server
        print(f"Uploading signature to server...")
        response = requests.post(
            f"{self.app_server_url}/transactions/{transaction_id}/buyer_sign",
            json={"buyer_signature": signed_doc["signatures"]["buyer"]}
        )
        
        if response.status_code == 200:
            print(f"✓ Buyer signature added successfully")
            return signed_doc
        else:
            print(f"✗ Failed to upload signature: {response.text}")
            return None
    
    def share_with_individual(self, transaction_id: int, recipient: str):
        """
        Share transaction with an individual (creates audit record)
        """
        print(f"\n=== Sharing Transaction {transaction_id} with {recipient} ===")
        
        # Create share record signature
        share_record = {
            "transaction_id": transaction_id,
            "shared_by": self.buyer_name,
            "shared_with": recipient
        }
        
        share_record_bytes = json.dumps(share_record, sort_keys=True).encode('utf-8')
        share_hash = crypto.hash_data(share_record_bytes)
        
        # Sign share record
        signing_key = self.key_manager.load_signing_private_key(self.buyer_name)
        signature = crypto.sign_data(signing_key, share_hash)
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        # Upload share record
        response = requests.post(
            f"{self.app_server_url}/transactions/{transaction_id}/share",
            json={
                "shared_by": self.buyer_name,
                "shared_with": recipient,
                "signature": signature_b64
            }
        )
        
        if response.status_code == 200:
            print(f"✓ Share record created")
            print(f"  This action is now auditable by the seller (SR4)")
            return True
        else:
            print(f"✗ Failed to create share record: {response.text}")
            return False
    
    def share_with_group(self, transaction_id: int, group_id: str):
        """
        Share transaction with a group (creates audit record)
        """
        print(f"\n=== Sharing Transaction {transaction_id} with Group {group_id} ===")
        
        # Create group share record signature
        share_record = {
            "transaction_id": transaction_id,
            "shared_by": self.buyer_name,
            "group_id": group_id
        }
        
        share_record_bytes = json.dumps(share_record, sort_keys=True).encode('utf-8')
        share_hash = crypto.hash_data(share_record_bytes)
        
        # Sign share record
        signing_key = self.key_manager.load_signing_private_key(self.buyer_name)
        signature = crypto.sign_data(signing_key, share_hash)
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        # Upload group share record
        response = requests.post(
            f"{self.app_server_url}/transactions/{transaction_id}/share_group",
            json={
                "shared_by": self.buyer_name,
                "group_id": group_id,
                "signature": signature_b64
            }
        )
        
        if response.status_code == 200:
            print(f"✓ Group share record created")
            return True
        else:
            print(f"✗ Failed to create group share record: {response.text}")
            return False


def demo_buyer():
    """Demo buyer operations"""
    print("=" * 60)
    print("BUYER CLIENT DEMO")
    print("=" * 60)
    
    buyer = BuyerClient("Lays Chips")
    
    # Register
    buyer.register()
    
    # Sign transaction (assuming it was created by seller)
    signed = buyer.sign_transaction(123)
    
    if signed:
        print(f"\n✓ Transaction signed successfully!")
        
        # Share with someone
        print(f"\nSharing with auditor...")
        buyer.share_with_individual(123, "Auditor Corp")
        
        print(f"\nSharing with group...")
        buyer.share_with_group(123, "tech_partners")
        
        print(f"\n✓ All operations completed!")
        print(f"Seller can now verify shares using seller_client.py")


if __name__ == "__main__":
    demo_buyer()
