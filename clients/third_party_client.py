"""
clients/third_party_client.py
Third-party client for accessing shared transactions
"""

import sys
import json
import requests
import os
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from chainofproduct.library import unprotect, check
from chainofproduct.keymanager import KeyManager, PublicKeyStore


class ThirdPartyClient:
    """Client for third-party access to transactions"""
    
    def __init__(self, company_name: str, app_server_url: Optional[str] = None):
        self.company_name = company_name
        self.app_server_url = app_server_url or os.getenv("APP_SERVER_URL", "http://localhost:8001")
        self.key_manager = KeyManager()
        self.public_key_store = PublicKeyStore()
    
    def register(self):
        """Register third party with application server"""
        print(f"Registering third party: {self.company_name}")
        
        # Generate keys if not exist
        try:
            public_keys = self.key_manager.export_public_keys(self.company_name)
        except FileNotFoundError:
            print(f"  Generating new keys for {self.company_name}...")
            public_keys = self.key_manager.generate_company_keys(self.company_name)
        
        # Register with server
        response = requests.post(
            f"{self.app_server_url}/register_company",
            json=public_keys
        )
        
        if response.status_code == 201:
            print(f"✓ Third party registered successfully")
            return True
        elif response.status_code == 409:
            print(f"✓ Third party already registered")
            return True
        else:
            print(f"✗ Registration failed: {response.text}")
            return False
    
    def access_transaction(self, transaction_id: int):
        """
        Access a transaction (if authorized)
        Demonstrates SR1 (Confidentiality) - only authorized parties can decrypt
        """
        print(f"\n=== Accessing Transaction {transaction_id} ===")
        
        # Retrieve transaction
        print(f"Retrieving transaction from server...")
        response = requests.get(f"{self.app_server_url}/transactions/{transaction_id}")
        
        if response.status_code != 200:
            print(f"✗ Failed to retrieve transaction: {response.text}")
            return None
        
        data = response.json()
        protected_doc = data["transaction"]["protected_document"]
        
        # Verify transaction integrity (SR2, SR3)
        print(f"Verifying transaction authenticity and integrity...")
        verification = check(protected_doc, self.public_key_store)
        
        print(f"Verification results:")
        print(f"  Valid: {verification['valid']}")
        print(f"  Seller signature: {verification['details'].get('seller_signature', 'N/A')}")
        print(f"  Buyer signature: {verification['details'].get('buyer_signature', 'N/A')}")
        
        if verification["errors"]:
            print(f"  Errors:")
            for error in verification["errors"]:
                print(f"    - {error}")
        
        if verification["warnings"]:
            print(f"  Warnings:")
            for warning in verification["warnings"]:
                print(f"    - {warning}")
        
        # Try to decrypt
        print(f"\nAttempting to decrypt transaction...")
        try:
            result = unprotect(protected_doc, self.company_name, self.key_manager)
            transaction_data = result["transaction"]
            
            print(f"✓ Access granted! Transaction decrypted successfully")
            print(f"  Access method: {result['access_method']}")
            print(f"\nTransaction Details:")
            print(f"  ID: {transaction_data['id']}")
            print(f"  Timestamp: {transaction_data['timestamp']}")
            print(f"  Seller: {transaction_data['seller']}")
            print(f"  Buyer: {transaction_data['buyer']}")
            print(f"  Product: {transaction_data['product']}")
            print(f"  Units: {transaction_data['units']:,}")
            print(f"  Amount: ${transaction_data['amount']:,}")
            
            return transaction_data
            
        except Exception as e:
            print(f"✗ Access denied: {e}")
            print(f"  This demonstrates SR1 (Confidentiality):")
            print(f"  Only authorized parties can decrypt transactions")
            return None
    
    def audit_shares(self, transaction_id: int):
        """
        Audit who has access to a transaction
        Demonstrates SR4 (Integrity 2) - tracking disclosures
        """
        print(f"\n=== Auditing Shares for Transaction {transaction_id} ===")
        
        # Get individual share records
        response = requests.get(
            f"{self.app_server_url}/transactions/{transaction_id}/shares"
        )
        
        if response.status_code == 200:
            share_records = response.json()["share_records"]
            print(f"\nIndividual Share Records: {len(share_records)}")
            for record in share_records:
                print(f"  {record['timestamp']}: {record['shared_by']} → {record['shared_with']}")
        
        # Get group share records
        response = requests.get(
            f"{self.app_server_url}/transactions/{transaction_id}/group_shares"
        )
        
        if response.status_code == 200:
            group_records = response.json()["group_share_records"]
            print(f"\nGroup Share Records: {len(group_records)}")
            for record in group_records:
                print(f"  {record['timestamp']}: {record['shared_by']} → Group {record['group_id']}")
        
        print(f"\n✓ This demonstrates SR4 (Integrity 2):")
        print(f"  All disclosures are auditable and verifiable")


def demo_third_party():
    """Demo third-party operations"""
    print("=" * 60)
    print("THIRD PARTY CLIENT DEMO")
    print("=" * 60)
    
    # Demo as authorized third party
    auditor = ThirdPartyClient("Auditor Corp")
    auditor.register()
    
    print(f"\n--- Attempting access as AUTHORIZED third party ---")
    transaction = auditor.access_transaction(123)
    
    if transaction:
        print(f"\n✓ Successfully accessed transaction as authorized party")
    
    # Audit share records
    auditor.audit_shares(123)
    
    print("\n" + "=" * 60)
    
    # Demo as unauthorized third party
    print(f"\n--- Attempting access as UNAUTHORIZED third party ---")
    unauthorized = ThirdPartyClient("Random Company")
    unauthorized.register()
    
    transaction = unauthorized.access_transaction(123)
    
    if not transaction:
        print(f"\n✓ Access correctly denied to unauthorized party")
        print(f"  This demonstrates proper enforcement of SR1 (Confidentiality)")


if __name__ == "__main__":
    demo_third_party()
