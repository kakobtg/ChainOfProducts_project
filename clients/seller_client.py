"""
clients/seller_client.py
Seller client for creating and managing transactions
"""

import sys
import json
import requests
import os
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from chainofproduct.library import protect
from chainofproduct.keymanager import KeyManager, PublicKeyStore


class SellerClient:
    """Client for seller operations"""
    
    def __init__(self, seller_name: str, app_server_url: Optional[str] = None,
                 group_server_url: Optional[str] = None):
        self.seller_name = seller_name
        self.app_server_url = app_server_url or os.getenv("APP_SERVER_URL", "http://localhost:8001")
        self.group_server_url = group_server_url or os.getenv("GROUP_SERVER_URL", "http://localhost:8002")
        self.key_manager = KeyManager()
        self.public_key_store = PublicKeyStore()
    
    def register(self):
        """Register seller with application server"""
        print(f"Registering seller: {self.seller_name}")
        
        # Generate keys if not exist
        try:
            public_keys = self.key_manager.export_public_keys(self.seller_name)
        except FileNotFoundError:
            print(f"  Generating new keys for {self.seller_name}...")
            public_keys = self.key_manager.generate_company_keys(self.seller_name)
        
        # Register with server
        response = requests.post(
            f"{self.app_server_url}/register_company",
            json=public_keys
        )
        
        if response.status_code == 201:
            print(f"✓ Seller registered successfully")
            return True
        elif response.status_code == 409:
            print(f"✓ Seller already registered")
            return True
        else:
            print(f"✗ Registration failed: {response.text}")
            return False
    
    def create_transaction(self, transaction_data: dict, recipients: list = None, 
                          groups: list = None):
        """
        Create and protect a transaction
        
        Args:
            transaction_data: DvP transaction dict
            recipients: Optional list of additional recipient companies
            groups: Optional list of group IDs
        """
        print(f"\n=== Creating Transaction {transaction_data['id']} ===")
        
        buyer_name = transaction_data["buyer"]
        
        # Protect transaction
        print(f"Protecting transaction...")
        protected_doc = protect(
            transaction_data,
            self.seller_name,
            buyer_name,
            self.key_manager,
            self.public_key_store,
            recipients=recipients,
            groups=groups,
            group_server_url=self.group_server_url
        )
        
        print(f"✓ Transaction protected")
        print(f"  Seller: {self.seller_name}")
        print(f"  Buyer: {buyer_name}")
        print(f"  Recipients: {len(protected_doc.get('wrapped_keys', {}))}")
        print(f"  Groups: {len(protected_doc.get('group_wrapped_keys', {}))}")
        
        # Upload to server
        print(f"Uploading to application server...")
        response = requests.post(
            f"{self.app_server_url}/transactions",
            json={"protected_document": protected_doc}
        )
        
        if response.status_code == 201:
            print(f"✓ Transaction uploaded successfully")
            return protected_doc
        else:
            print(f"✗ Upload failed: {response.text}")
            return None
    
    def verify_shares(self, transaction_id: int):
        """
        Verify who the buyer has shared the transaction with (SR4)
        """
        print(f"\n=== Verifying Shares for Transaction {transaction_id} ===")
        
        # Get share records
        response = requests.get(
            f"{self.app_server_url}/transactions/{transaction_id}/shares"
        )
        
        if response.status_code != 200:
            print(f"✗ Failed to get share records: {response.text}")
            return None
        
        share_records = response.json()["share_records"]
        
        print(f"Individual shares: {len(share_records)}")
        for record in share_records:
            print(f"  - {record['shared_by']} → {record['shared_with']} at {record['timestamp']}")
        
        # Get group share records
        response = requests.get(
            f"{self.app_server_url}/transactions/{transaction_id}/group_shares"
        )
        
        if response.status_code == 200:
            group_records = response.json()["group_share_records"]
            print(f"Group shares: {len(group_records)}")
            for record in group_records:
                print(f"  - {record['shared_by']} → Group:{record['group_id']} at {record['timestamp']}")
        
        return share_records


def demo_seller():
    """Demo seller operations"""
    print("=" * 60)
    print("SELLER CLIENT DEMO")
    print("=" * 60)
    
    seller = SellerClient("Ching Chong Extractions")
    
    # Register
    seller.register()
    
    # Create transaction
    transaction = {
        "id": 123,
        "timestamp": 1766336340,
        "seller": "Ching Chong Extractions",
        "buyer": "Lays Chips",
        "product": "Indium",
        "units": 40000,
        "amount": 90000000
    }
    
    protected = seller.create_transaction(
        transaction,
        recipients=["Auditor Corp"],
        groups=["tech_partners"]
    )
    
    if protected:
        print(f"\n✓ Transaction {transaction['id']} created successfully!")
        print(f"\nWaiting for buyer to sign...")
        print(f"Buyer should run: buyer_client.py to sign transaction")
    
    # Later, verify shares
    # seller.verify_shares(123)


if __name__ == "__main__":
    demo_seller()
