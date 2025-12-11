"""
chainofproduct/keymanager.py
Key management for companies and users
"""

import os
import json
import base64
from pathlib import Path
from typing import Dict, Any, Tuple
from . import crypto


class KeyManager:
    """Manages cryptographic keys for companies"""
    
    def __init__(self, storage_dir: str = "keys"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True, parents=True)
    
    def generate_company_keys(self, company_name: str) -> Dict[str, Any]:
        """
        Generate all keys for a company
        Returns dict with public keys (for sharing) and saves private keys
        """
        # Generate signing keys
        sign_private, sign_public = crypto.generate_signing_keypair()
        
        # Generate encryption keys
        enc_private, enc_public = crypto.generate_encryption_keypair()
        
        # Save private keys
        company_dir = self.storage_dir / company_name
        company_dir.mkdir(exist_ok=True, parents=True)
        
        with open(company_dir / "signing_private.key", "wb") as f:
            f.write(crypto.serialize_private_key(sign_private))
        
        with open(company_dir / "encryption_private.key", "wb") as f:
            f.write(crypto.serialize_private_key(enc_private))
        
        # Return public keys for registration
        return {
            "company_name": company_name,
            "signing_public_key": base64.b64encode(crypto.serialize_public_key(sign_public)).decode('utf-8'),
            "encryption_public_key": base64.b64encode(crypto.serialize_public_key(enc_public)).decode('utf-8')
        }
    
    def load_signing_private_key(self, company_name: str):
        """Load signing private key for a company"""
        key_path = self.storage_dir / company_name / "signing_private.key"
        if not key_path.exists():
            raise FileNotFoundError(f"Signing private key not found for {company_name}")
        
        with open(key_path, "rb") as f:
            key_bytes = f.read()
        
        return crypto.deserialize_signing_private_key(key_bytes)
    
    def load_encryption_private_key(self, company_name: str):
        """Load encryption private key for a company"""
        key_path = self.storage_dir / company_name / "encryption_private.key"
        if not key_path.exists():
            raise FileNotFoundError(f"Encryption private key not found for {company_name}")
        
        with open(key_path, "rb") as f:
            key_bytes = f.read()
        
        return crypto.deserialize_encryption_private_key(key_bytes)
    
    def export_public_keys(self, company_name: str) -> Dict[str, str]:
        """Export public keys for a company (reconstructed from private keys)"""
        sign_private = self.load_signing_private_key(company_name)
        enc_private = self.load_encryption_private_key(company_name)
        
        sign_public = sign_private.public_key()
        enc_public = enc_private.public_key()
        
        return {
            "company_name": company_name,
            "signing_public_key": base64.b64encode(crypto.serialize_public_key(sign_public)).decode('utf-8'),
            "encryption_public_key": base64.b64encode(crypto.serialize_public_key(enc_public)).decode('utf-8')
        }
    
    def list_companies(self) -> list:
        """List all companies with stored keys"""
        companies = []
        for item in self.storage_dir.iterdir():
            if item.is_dir():
                companies.append(item.name)
        return companies


class PublicKeyStore:
    """
    Stores public keys of other companies
    In production, this would query the Application Server
    """
    
    def __init__(self, storage_file: str = "public_keys.json"):
        self.storage_file = Path(storage_file)
        self.keys = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load stored public keys"""
        if self.storage_file.exists():
            with open(self.storage_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save(self):
        """Save public keys to disk"""
        with open(self.storage_file, 'w') as f:
            json.dump(self.keys, f, indent=2)
    
    def add_company(self, company_data: Dict[str, str]):
        """Add or update public keys for a company"""
        company_name = company_data["company_name"]
        self.keys[company_name] = {
            "signing_public_key": company_data["signing_public_key"],
            "encryption_public_key": company_data["encryption_public_key"]
        }
        self._save()
    
    def get_company(self, company_name: str) -> Dict[str, str]:
        """Get public keys for a company"""
        if company_name not in self.keys:
            raise KeyError(f"Public keys not found for {company_name}")
        return self.keys[company_name]
    
    def get_signing_public_key(self, company_name: str):
        """Get signing public key object for a company"""
        data = self.get_company(company_name)
        key_bytes = base64.b64decode(data["signing_public_key"])
        return crypto.deserialize_signing_public_key(key_bytes)
    
    def get_encryption_public_key(self, company_name: str):
        """Get encryption public key object for a company"""
        data = self.get_company(company_name)
        key_bytes = base64.b64decode(data["encryption_public_key"])
        return crypto.deserialize_encryption_public_key(key_bytes)
    
    def list_companies(self) -> list:
        """List all companies with stored public keys"""
        return list(self.keys.keys())