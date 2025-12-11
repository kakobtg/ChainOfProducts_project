"""
chainofproduct/crypto.py
Core cryptographic operations using the cryptography library.
NO custom crypto primitives - only battle-tested libraries.
"""

import os
import json
from typing import Tuple, Dict, Any
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend

class CryptoError(Exception):
    """Base exception for crypto operations"""
    pass


def generate_signing_keypair() -> Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate Ed25519 signing key pair"""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def generate_encryption_keypair() -> Tuple[x25519.X25519PrivateKey, x25519.X25519PublicKey]:
    """Generate X25519 encryption key pair"""
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def sign_data(private_key: ed25519.Ed25519PrivateKey, data: bytes) -> bytes:
    """Sign data using Ed25519"""
    return private_key.sign(data)


def verify_signature(public_key: ed25519.Ed25519PublicKey, signature: bytes, data: bytes) -> bool:
    """Verify Ed25519 signature"""
    try:
        public_key.verify(signature, data)
        return True
    except Exception:
        return False


def hash_data(data: bytes) -> bytes:
    """SHA-256 hash of data"""
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(data)
    return digest.finalize()


def generate_symmetric_key() -> bytes:
    """Generate 256-bit random symmetric key"""
    return os.urandom(32)


def encrypt_aes_gcm(key: bytes, plaintext: bytes) -> Dict[str, str]:
    """
    Encrypt with AES-GCM
    Returns dict with ciphertext, nonce, and tag (all base64 encoded)
    """
    import base64
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    return {
        "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
        "nonce": base64.b64encode(nonce).decode('utf-8')
    }


def decrypt_aes_gcm(key: bytes, encrypted_data: Dict[str, str]) -> bytes:
    """
    Decrypt AES-GCM encrypted data
    """
    import base64
    aesgcm = AESGCM(key)
    nonce = base64.b64decode(encrypted_data["nonce"])
    ciphertext = base64.b64decode(encrypted_data["ciphertext"])
    
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext
    except Exception as e:
        raise CryptoError(f"Decryption failed: {e}")


def wrap_key_x25519(recipient_public_key: x25519.X25519PublicKey, key_to_wrap: bytes) -> Dict[str, str]:
    """
    Wrap a symmetric key for a recipient using X25519 + HKDF + AES-GCM
    Returns ephemeral public key and encrypted key
    """
    import base64
    
    # Generate ephemeral key pair
    ephemeral_private = x25519.X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()
    
    # Perform ECDH
    shared_secret = ephemeral_private.exchange(recipient_public_key)
    
    # Derive encryption key using HKDF
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'key_wrapping',
        backend=default_backend()
    )
    wrapping_key = kdf.derive(shared_secret)
    
    # Encrypt the key to wrap
    encrypted = encrypt_aes_gcm(wrapping_key, key_to_wrap)
    
    return {
        "ephemeral_public_key": base64.b64encode(
            ephemeral_public.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
        ).decode('utf-8'),
        "encrypted_key": encrypted
    }


def unwrap_key_x25519(recipient_private_key: x25519.X25519PrivateKey, wrapped_data: Dict[str, str]) -> bytes:
    """
    Unwrap a symmetric key using X25519 + HKDF + AES-GCM
    """
    import base64
    
    # Load ephemeral public key
    ephemeral_public_bytes = base64.b64decode(wrapped_data["ephemeral_public_key"])
    ephemeral_public = x25519.X25519PublicKey.from_public_bytes(ephemeral_public_bytes)
    
    # Perform ECDH
    shared_secret = recipient_private_key.exchange(ephemeral_public)
    
    # Derive decryption key using HKDF
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'key_wrapping',
        backend=default_backend()
    )
    wrapping_key = kdf.derive(shared_secret)
    
    # Decrypt the wrapped key
    unwrapped_key = decrypt_aes_gcm(wrapping_key, wrapped_data["encrypted_key"])
    
    return unwrapped_key


def derive_group_key(transaction_key: bytes, group_id: str, tx_id: str) -> bytes:
    """
    Derive a group-specific key from transaction key using HKDF
    This ensures different groups get different keys even for same transaction
    """
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"group:{group_id}:tx:{tx_id}".encode('utf-8'),
        backend=default_backend()
    )
    return kdf.derive(transaction_key)


def serialize_private_key(private_key) -> bytes:
    """Serialize private key to bytes"""
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    elif isinstance(private_key, x25519.X25519PrivateKey):
        return private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    else:
        raise CryptoError(f"Unsupported key type: {type(private_key)}")


def serialize_public_key(public_key) -> bytes:
    """Serialize public key to bytes"""
    if isinstance(public_key, (ed25519.Ed25519PublicKey, x25519.X25519PublicKey)):
        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    else:
        raise CryptoError(f"Unsupported key type: {type(public_key)}")


def deserialize_signing_private_key(key_bytes: bytes) -> ed25519.Ed25519PrivateKey:
    """Deserialize Ed25519 private key"""
    return ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)


def deserialize_signing_public_key(key_bytes: bytes) -> ed25519.Ed25519PublicKey:
    """Deserialize Ed25519 public key"""
    return ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)


def deserialize_encryption_private_key(key_bytes: bytes) -> x25519.X25519PrivateKey:
    """Deserialize X25519 private key"""
    return x25519.X25519PrivateKey.from_private_bytes(key_bytes)


def deserialize_encryption_public_key(key_bytes: bytes) -> x25519.X25519PublicKey:
    """Deserialize X25519 public key"""
    return x25519.X25519PublicKey.from_public_bytes(key_bytes)