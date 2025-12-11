# ChainOfProduct - Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies

```bash
pip install cryptography fastapi uvicorn pydantic requests
```

### 2. Create Directory Structure

```
chainofproduct/
├── chainofproduct/
│   ├── __init__.py
│   ├── crypto.py
│   ├── keymanager.py
│   ├── library.py
│   └── cli.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── db.py
│   └── models.py
├── groupserver/
│   ├── __init__.py
│   └── main.py
├── clients/
│   ├── __init__.py
│   ├── seller_client.py
│   ├── buyer_client.py
│   └── third_party_client.py
├── requirements.txt
└── README.md
```

### 3. Start Servers (3 Terminals)

**Terminal 1 - Group Server:**
```bash
python -m groupserver.main
# Runs on http://localhost:8002
```

**Terminal 2 - Application Server:**
```bash
python -m app.main
# Runs on http://localhost:8001
```

**Terminal 3 - Run Demo:**
```bash
# Generate keys for all parties
python -m chainofproduct.cli keygen "Ching Chong Extractions"
python -m chainofproduct.cli keygen "Lays Chips"
python -m chainofproduct.cli keygen "Auditor Corp"

# Create a group
curl -X POST http://localhost:8002/groups/create \
  -H "Content-Type: application/json" \
  -d '{"group_id": "tech_partners", "members": ["Auditor Corp"]}'

# Run workflows
python clients/seller_client.py
python clients/buyer_client.py
python clients/third_party_client.py
```

## What Gets Demonstrated

### ✓ SR1: Confidentiality
- Transactions encrypted with AES-256-GCM
- Only authorized parties can decrypt
- Application server never sees plaintext

### ✓ SR2: Authentication
- Ed25519 signatures from seller and buyer
- Only legitimate parties can create official shares
- Signatures verified on access

### ✓ SR3: Integrity 1
- Authenticated encryption prevents tampering
- Any modification detected on decryption
- Cryptographic hash of transaction content

### ✓ SR4: Integrity 2
- All shares cryptographically signed and recorded
- Seller can audit who buyer shared with
- Complete audit trail of disclosures

### ✓ Dynamic Groups
- Transactions can be shared with groups
- Only current members at disclosure time get access
- New members don't get old keys
- Removed members can't access future transactions

## Command Reference

```bash
# Key management
cop keygen "Company Name"

# Protect transaction
cop protect input.json output.protected.json \
  --recipients "Company1,Company2" \
  --groups "group1,group2"

# Verify document
cop check protected.json

# Decrypt document
cop unprotect protected.json "Company Name" output.json

# Add buyer signature
cop buyer-sign protected.json "Buyer Name" signed.json
```

## Architecture at a Glance

```
Client (VM1) → HTTPS → App Server (VM2/DMZ) → DB (VM3)
                  ↓
            Group Server (VM4)
```

**Key Point:** Application Server (DMZ) never sees plaintext!

## Security Guarantees

| Requirement | Implementation | Library |
|------------|----------------|---------|
| Encryption | AES-256-GCM | cryptography |
| Signatures | Ed25519 | cryptography |
| Key Exchange | X25519 | cryptography |
| Key Derivation | HKDF-SHA256 | cryptography |
| Hashing | SHA-256 | cryptography |

**No custom cryptography - all battle-tested primitives!**

## Common Commands

### Setup New Company
```bash
python -m chainofproduct.cli keygen "Company Name"
```

### Create Group
```bash
curl -X POST http://localhost:8002/groups/create \
  -H "Content-Type: application/json" \
  -d '{"group_id": "partners", "members": ["Company1", "Company2"]}'
```

### Protect Transaction
```python
from chainofproduct.library import protect
from chainofproduct.keymanager import KeyManager, PublicKeyStore

km = KeyManager()
pks = PublicKeyStore()

protected = protect(
    transaction_data,
    "Seller Company",
    "Buyer Company",
    km,
    pks,
    recipients=["Auditor"],
    groups=["partners"]
)
```

### Verify and Decrypt
```python
from chainofproduct.library import check, unprotect

# Verify
results = check(protected_doc, pks)
print(f"Valid: {results['valid']}")

# Decrypt (if authorized)
decrypted = unprotect(protected_doc, "My Company", km)
print(decrypted["transaction"])
```

## Troubleshooting

### Servers Not Starting
```bash
# Check ports
lsof -i :8001  # App server
lsof -i :8002  # Group server

# Kill if needed
kill -9 <PID>
```

### Keys Not Found
```bash
# Regenerate keys
python -m chainofproduct.cli keygen "Company Name"

# Check keys directory
ls -la keys/
```

### Cannot Decrypt
- Verify you're in recipients list or group members
- Check company name matches exactly
- Ensure keys were generated correctly

## Next Steps

1. Read full [README.md](README.md) for detailed documentation
2. Review cryptographic design in [crypto.py](chainofproduct/crypto.py)
3. Explore API endpoints in [app/main.py](app/main.py)
4. Set up TLS certificates for production
5. Configure firewalls as documented

## Production Checklist

- [ ] Replace SQLite with PostgreSQL/MySQL
- [ ] Set up TLS with CA-signed certificates
- [ ] Configure firewalls between VMs
- [ ] Implement proper key storage (HSM/KMS)
- [ ] Add authentication (OAuth2/JWT)
- [ ] Enable audit logging
- [ ] Set up monitoring and alerting
- [ ] Regular backups of database
- [ ] Key rotation policies
- [ ] Security testing and penetration testing

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Review security considerations in README.md
- Check cryptography library documentation

---

**Remember:** This system handles sensitive supply chain data. Always follow security best practices in production!