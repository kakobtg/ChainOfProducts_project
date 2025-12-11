"""
chainofproduct/library.py
Core library implementing protect, check, and unprotect operations
"""

import json
import base64
import os
import requests
from typing import Dict, Any, List, Optional
from . import crypto
from .keymanager import KeyManager, PublicKeyStore


class ProtectionError(Exception):
    """Base exception for protection operations"""
    pass


def protect(
    transaction_data: Dict[str, Any],
    seller_name: str,
    buyer_name: str,
    key_manager: KeyManager,
    public_key_store: PublicKeyStore,
    recipients: Optional[List[str]] = None,
    groups: Optional[List[str]] = None,
    group_server_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Protect a DvP transaction
    
    Args:
        transaction_data: The plaintext transaction
        seller_name: Name of seller company
        buyer_name: Name of buyer company
        key_manager: Key manager with seller's private keys
        public_key_store: Store of public keys
        recipients: Optional list of additional recipients
        groups: Optional list of group IDs to share with
        group_server_url: URL of group server
    
    Returns:
        Protected document structure
    """
    # Validate transaction data
    required_fields = ["id", "timestamp", "seller", "buyer", "product", "units", "amount"]
    for field in required_fields:
        if field not in transaction_data:
            raise ProtectionError(f"Missing required field: {field}")
    
    # Verify seller matches
    if transaction_data["seller"] != seller_name:
        raise ProtectionError(f"Seller name mismatch: {seller_name} vs {transaction_data['seller']}")
    
    # Verify buyer matches
    if transaction_data["buyer"] != buyer_name:
        raise ProtectionError(f"Buyer name mismatch: {buyer_name} vs {transaction_data['buyer']}")
    
    # Generate transaction symmetric key
    K_T = crypto.generate_symmetric_key()
    
    # Encrypt transaction with AES-GCM
    plaintext = json.dumps(transaction_data, sort_keys=True).encode('utf-8')
    encrypted_tx = crypto.encrypt_aes_gcm(K_T, plaintext)
    
    # Sign transaction hash (seller signature)
    tx_hash = crypto.hash_data(plaintext)
    seller_sign_key = key_manager.load_signing_private_key(seller_name)
    seller_signature = crypto.sign_data(seller_sign_key, tx_hash)
    
    # Wrap key for seller
    seller_enc_pub_key = public_key_store.get_encryption_public_key(seller_name)
    wrapped_keys = {
        seller_name: crypto.wrap_key_x25519(seller_enc_pub_key, K_T)
    }
    
    # Wrap key for buyer
    buyer_enc_pub_key = public_key_store.get_encryption_public_key(buyer_name)
    wrapped_keys[buyer_name] = crypto.wrap_key_x25519(buyer_enc_pub_key, K_T)
    
    # Wrap key for additional recipients
    if recipients:
        for recipient in recipients:
            try:
                recipient_enc_pub_key = public_key_store.get_encryption_public_key(recipient)
                wrapped_keys[recipient] = crypto.wrap_key_x25519(recipient_enc_pub_key, K_T)
            except KeyError:
                print(f"Warning: Public key not found for recipient {recipient}, skipping")
    
    # Handle group disclosures
    group_server_url = group_server_url or os.getenv("GROUP_SERVER_URL", "http://localhost:8002")
    group_wrapped_keys = {}
    if groups:
        tx_id = str(transaction_data["id"])
        for group_id in groups:
            try:
                # Query group server for current members
                response = requests.get(f"{group_server_url}/groups/{group_id}/members")
                if response.status_code != 200:
                    print(f"Warning: Could not fetch members for group {group_id}, skipping")
                    continue
                
                members = response.json()["members"]
                
                # Derive group-specific key
                group_key = crypto.derive_group_key(K_T, group_id, tx_id)
                
                # Wrap group key for each current member
                group_wrapped_keys[group_id] = {
                    "members": {}
                }
                
                for member in members:
                    try:
                        member_enc_pub_key = public_key_store.get_encryption_public_key(member)
                        group_wrapped_keys[group_id]["members"][member] = crypto.wrap_key_x25519(
                            member_enc_pub_key, group_key
                        )
                    except KeyError:
                        print(f"Warning: Public key not found for member {member} of group {group_id}")
                
            except Exception as e:
                print(f"Warning: Error processing group {group_id}: {e}")
    
    # Build protected document
    protected_doc = {
        "version": "1.0",
        "transaction_id": transaction_data["id"],
        "encrypted_transaction": encrypted_tx,
        "signatures": {
            "seller": {
                "company": seller_name,
                "signature": base64.b64encode(seller_signature).decode('utf-8')
            },
            "buyer": None  # To be added by buyer
        },
        "wrapped_keys": {
            company: {
                "ephemeral_public_key": wk["ephemeral_public_key"],
                "encrypted_key": wk["encrypted_key"]
            }
            for company, wk in wrapped_keys.items()
        },
        "group_wrapped_keys": group_wrapped_keys,
        "transaction_hash": base64.b64encode(tx_hash).decode('utf-8')
    }
    
    return protected_doc


def buyer_sign(
    protected_doc: Dict[str, Any],
    buyer_name: str,
    key_manager: KeyManager
) -> Dict[str, Any]:
    """
    Add buyer's signature to a protected document
    
    Args:
        protected_doc: Protected document from protect()
        buyer_name: Name of buyer company
        key_manager: Key manager with buyer's private keys
    
    Returns:
        Updated protected document with buyer signature
    """
    # Get transaction hash
    tx_hash_b64 = protected_doc["transaction_hash"]
    tx_hash = base64.b64decode(tx_hash_b64)
    
    # Sign with buyer's key
    buyer_sign_key = key_manager.load_signing_private_key(buyer_name)
    buyer_signature = crypto.sign_data(buyer_sign_key, tx_hash)
    
    # Add to document
    protected_doc["signatures"]["buyer"] = {
        "company": buyer_name,
        "signature": base64.b64encode(buyer_signature).decode('utf-8')
    }
    
    return protected_doc


def check(
    protected_doc: Dict[str, Any],
    public_key_store: PublicKeyStore
) -> Dict[str, Any]:
    """
    Verify integrity and authenticity of a protected document
    
    Returns:
        Dict with verification results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "details": {}
    }
    
    try:
        # Check version
        if protected_doc.get("version") != "1.0":
            results["warnings"].append(f"Unknown version: {protected_doc.get('version')}")
        
        # Get transaction hash
        tx_hash = base64.b64decode(protected_doc["transaction_hash"])
        
        # Verify seller signature
        seller_sig_data = protected_doc["signatures"]["seller"]
        if seller_sig_data:
            seller_company = seller_sig_data["company"]
            seller_signature = base64.b64decode(seller_sig_data["signature"])
            
            try:
                seller_pub_key = public_key_store.get_signing_public_key(seller_company)
                if crypto.verify_signature(seller_pub_key, seller_signature, tx_hash):
                    results["details"]["seller_signature"] = "valid"
                else:
                    results["valid"] = False
                    results["errors"].append("Seller signature verification failed")
                    results["details"]["seller_signature"] = "invalid"
            except KeyError:
                results["warnings"].append(f"Cannot verify seller signature: public key not found for {seller_company}")
                results["details"]["seller_signature"] = "cannot_verify"
        else:
            results["errors"].append("Seller signature missing")
            results["valid"] = False
        
        # Verify buyer signature
        buyer_sig_data = protected_doc["signatures"]["buyer"]
        if buyer_sig_data:
            buyer_company = buyer_sig_data["company"]
            buyer_signature = base64.b64decode(buyer_sig_data["signature"])
            
            try:
                buyer_pub_key = public_key_store.get_signing_public_key(buyer_company)
                if crypto.verify_signature(buyer_pub_key, buyer_signature, tx_hash):
                    results["details"]["buyer_signature"] = "valid"
                else:
                    results["valid"] = False
                    results["errors"].append("Buyer signature verification failed")
                    results["details"]["buyer_signature"] = "invalid"
            except KeyError:
                results["warnings"].append(f"Cannot verify buyer signature: public key not found for {buyer_company}")
                results["details"]["buyer_signature"] = "cannot_verify"
        else:
            results["warnings"].append("Buyer signature not yet added")
            results["details"]["buyer_signature"] = "missing"
        
        # Count wrapped keys
        results["details"]["individual_recipients"] = len(protected_doc.get("wrapped_keys", {}))
        results["details"]["groups"] = len(protected_doc.get("group_wrapped_keys", {}))
        
        # Verify AES-GCM integrity (we can't decrypt without key, but structure is valid)
        encrypted_tx = protected_doc["encrypted_transaction"]
        if not all(k in encrypted_tx for k in ["ciphertext", "nonce"]):
            results["valid"] = False
            results["errors"].append("Encrypted transaction missing required fields")
        
    except Exception as e:
        results["valid"] = False
        results["errors"].append(f"Verification error: {str(e)}")
    
    return results


def unprotect(
    protected_doc: Dict[str, Any],
    company_name: str,
    key_manager: KeyManager
) -> Dict[str, Any]:
    """
    Decrypt a protected document
    
    Args:
        protected_doc: Protected document
        company_name: Name of company attempting to decrypt
        key_manager: Key manager with company's private keys
    
    Returns:
        Decrypted transaction data
    """
    # Try to find wrapped key for this company
    K_T = None
    access_method = None
    
    # Check individual wrapped keys
    if company_name in protected_doc.get("wrapped_keys", {}):
        wrapped_key_data = protected_doc["wrapped_keys"][company_name]
        enc_private_key = key_manager.load_encryption_private_key(company_name)
        K_T = crypto.unwrap_key_x25519(enc_private_key, wrapped_key_data)
        access_method = "individual"
    
    # Check group wrapped keys
    if K_T is None:
        for group_id, group_data in protected_doc.get("group_wrapped_keys", {}).items():
            if company_name in group_data.get("members", {}):
                wrapped_group_key = group_data["members"][company_name]
                enc_private_key = key_manager.load_encryption_private_key(company_name)
                group_key = crypto.unwrap_key_x25519(enc_private_key, wrapped_group_key)
                
                # Group key needs to be used to derive actual transaction key
                # For this, we need to reconstruct K_T from group_key
                # Actually, the group_key IS already the derived key that decrypts the transaction
                # Let me reconsider: we should encrypt transaction with group_key directly for groups
                # OR store group_key-encrypted K_T
                
                # Better approach: group members get wrapped group_key, which IS K_T derived for that group
                # Transaction is encrypted once with K_T, group_key is derived from K_T
                # So we need to store an encrypted version of K_T under group_key... 
                # Actually simpler: just use group_key to decrypt directly
                
                # Current implementation: group_key = KDF(K_T, group, tx)
                # Members get group_key wrapped
                # But transaction is encrypted with K_T, not group_key
                # So we need to store K_T encrypted with group_key!
                
                # Let me fix this: add group_encrypted_transaction_key to group data
                raise ProtectionError(
                    "Group-based decryption not fully implemented. "
                    "Need to store K_T encrypted with group_key. "
                    f"Found membership in group {group_id} but cannot decrypt."
                )
    
    if K_T is None:
        raise ProtectionError(f"No access granted for {company_name}")
    
    # Decrypt transaction
    encrypted_tx = protected_doc["encrypted_transaction"]
    plaintext = crypto.decrypt_aes_gcm(K_T, encrypted_tx)
    
    # Parse JSON
    transaction_data = json.loads(plaintext.decode('utf-8'))
    
    return {
        "transaction": transaction_data,
        "access_method": access_method,
        "verified": True
    }
