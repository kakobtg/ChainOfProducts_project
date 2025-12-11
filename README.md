# ChainOfProduct (CoP) - Secure Transaction System

A cryptographically secure system for managing confidential supply chain transactions with selective disclosure, authentication, and audit trails.

## Overview

ChainOfProduct enables secure Delivery-versus-Payment (DvP) transactions across supply chains where:
- **Confidentiality (SR1)**: Only authorized parties can read transactions
- **Authentication (SR2)**: Only seller/buyer can create official shares
- **Integrity 1 (SR3)**: Transactions are tamper-evident
- **Integrity 2 (SR4)**: Disclosures are auditable
- **Dynamic Groups**: Transactions can be shared with partner groups with time-based access control

## Architecture (3-VM)

```
┌─────────────────┐
│   VM1: Client   │
│  - CLI Tool     │
│  - Client Apps  │
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────────┐
│ VM2: App + Group    │
│ (DMZ)               │
│ - FastAPI           │
│ - Group mgmt        │
│ - Never sees        │
│   plaintext         │
└────────┬────────────┘
         │ DB Protocol
         ↓
┌─────────────────────┐
│ VM3: Database       │
│ - PostgreSQL        │
│ - Protected docs    │
│ - Share records     │
└─────────────────────┘
```

### Security Model

1. **Encryption**: Each transaction uses a unique AES-256-GCM key
2. **Key Wrapping**: Transaction keys wrapped with X25519 + HKDF
3. **Signatures**: Ed25519 signatures for authentication
4. **Group Access**: Group-specific keys derived using HKDF, wrapped for current members only
5. **Audit Trail**: All shares cryptographically signed and recorded

## Installation

### Dependencies

```bash
pip install -r requirements.txt
```

### Required Libraries
- `cryptography>=41.0.0` - Cryptographic primitives
- `fastapi>=0.104.0` - Application server
- `uvicorn>=0.24.0` - ASGI server
- `pydantic>=2.0.0` - Data validation
- `requests>=2.31.0` - HTTP client

## Project Structure

```
chainofproduct/
├── chainofproduct/          # Core library
│   ├── __init__.py
│   ├── crypto.py           # Cryptographic operations
│   ├── keymanager.py       # Key management
│   ├── library.py          # protect/check/unprotect
│   └── cli.py              # Command-line interface
├── app/                     # Application Server (VM2)
│   ├── __init__.py
│   ├── main.py             # FastAPI server
│   ├── db.py               # Database operations
│   └── models.py           # Data models
├── groupserver/             # Group Server (runs with App on VM2)
│   ├── __init__.py
│   └── main.py             # Group management API
├── clients/                 # Client scripts (VM1)
│   ├── seller_client.py
│   ├── buyer_client.py
│   └── third_party_client.py
├── requirements.txt
└── README.md
```

## Setup Instructions

### VM1: Client Machine

```bash
# Clone repository
git clone <repo-url>
cd chainofproduct

# Install dependencies
pip install -r requirements.txt

# Generate keys for companies
python -m chainofproduct.cli keygen "Ching Chong Extractions"
python -m chainofproduct.cli keygen "Lays Chips"
python -m chainofproduct.cli keygen "Auditor Corp"
```

### VM4: Group Server

```bash
# Start group server on port 8002
python -m groupserver.main

# Or with custom settings
python -c "from groupserver.main import start_server; start_server(host='0.0.0.0', port=8002)"
```

**Create test groups:**
```bash
curl -X POST http://localhost:8002/groups/create \
  -H "Content-Type: application/json" \
  -d '{"group_id": "tech_partners", "members": ["Auditor Corp", "Lays Chips"]}'
```

### VM3: Database Server (PostgreSQL)
- Install Postgres and create a database/user (see `scripts/setup_vm3_db.sh`).
- Expose port 5432 only to VM2.
- Connection string example (use your values): `postgresql://copuser:StrongPass@<VM3_IP>:5432/chainofproduct`

### VM2: Application + Group Server (DMZ)
- Requires `DATABASE_URL` pointing to VM3.
- Start application server on port 8001 and group server on 8002:
```bash
export DATABASE_URL=postgresql://copuser:StrongPass@<VM3_IP>:5432/chainofproduct
python -c "from app.main import start_server; start_server(host='0.0.0.0', port=8001)"
python -c "from groupserver.main import start_server; start_server(host='0.0.0.0', port=8002)"
```

## Running on Separate VMs (non-localhost)

1. **Assign fixed IPs** (examples: VM1=10.0.0.11, VM2=10.0.0.12, VM3=10.0.0.13).
2. **Start servers bound to all interfaces** on VM2 (app+group) with `DATABASE_URL` pointing at VM3.
3. **Point clients at the remote servers** (VM1 or any other machine):
   ```bash
   export APP_SERVER_URL=http://10.0.0.12:8001
   export GROUP_SERVER_URL=http://10.0.0.12:8002
   python clients/seller_client.py
   python clients/buyer_client.py
   python clients/third_party_client.py
   ```
   You can also pass URLs directly when constructing `SellerClient`, `BuyerClient`, or `ThirdPartyClient` if you embed these classes elsewhere.
4. **Open firewall rules** so VM1 can reach VM2:8001/8002 and VM2 can reach VM3:5432 (see rules below).

## Firewall Configuration
You can use either `iptables` or `ufw`. Open only what you need:

### Quick `ufw` example (recommended)
- VM1 (Client): `ufw allow out to <VM2_IP> port 8001 proto tcp`
- VM2 (App + Group): `ufw allow in on eth0 from <VM1_IP> to any port 8001,8002 proto tcp`; `ufw allow out to <VM3_IP> port 5432 proto tcp`
- VM3 (DB): `ufw allow in on eth0 from <VM2_IP> to any port 5432 proto tcp`
- Default policies: `ufw default deny incoming`; `ufw default deny outgoing` (or at least deny incoming); enable: `ufw enable`

### `iptables` example

#### VM1 (Client)
```bash
# Allow outbound HTTPS to VM2
iptables -A OUTPUT -p tcp -d <VM2_IP> --dport 8001 -j ACCEPT
```

#### VM2 (Application Server - DMZ)
```bash
# Allow inbound HTTPS from VM1
iptables -A INPUT -p tcp -s <VM1_IP> --dport 8001 -j ACCEPT
iptables -A INPUT -p tcp -s <VM1_IP> --dport 8002 -j ACCEPT

# Allow outbound to VM3 (database)
iptables -A OUTPUT -p tcp -d <VM3_IP> --dport 5432 -j ACCEPT

# Drop everything else
iptables -A INPUT -j DROP
iptables -A OUTPUT -j DROP
```

#### VM3 (Database Server)
```bash
# Only allow inbound from VM2
iptables -A INPUT -p tcp -s <VM2_IP> --dport 5432 -j ACCEPT
iptables -A INPUT -j DROP
```

## Start Guides by VM

### Assigning Fixed IPs on Kali (NetworkManager CLI)
Use `nmcli` (works on Kali). Substitute `eth0` and IPs as needed.
```bash
# Show connections and devices
nmcli con show
nmcli dev status

# Set a static IPv4 on eth0
nmcli con mod "Wired connection 1" ipv4.addresses 10.0.0.11/24
nmcli con mod "Wired connection 1" ipv4.gateway 10.0.0.1
nmcli con mod "Wired connection 1" ipv4.dns "8.8.8.8 1.1.1.1"
nmcli con mod "Wired connection 1" ipv4.method manual
nmcli con up "Wired connection 1"
```
Example layout (adjust to your LAN):
- VM1 (Client): 10.0.0.11
- VM2 (App + Group): 10.0.0.12
- VM3 (DB): 10.0.0.13

If you only have **three machines**, this is the intended layout: VM2 runs both the application and group server; VM3 is the dedicated Postgres DB; VM1 (or your laptop) runs clients. Just set the env vars to the correct IPs.

### VM1: Client
1. Install deps: `pip install -r requirements.txt`
2. Set endpoints:  
   `export APP_SERVER_URL=http://<VM2_IP>:8001`  
   `export GROUP_SERVER_URL=http://<VM2_IP>:8002`
3. Generate keys (once per company):  
   `python -m chainofproduct.cli keygen "Ching Chong Extractions"`  
   `python -m chainofproduct.cli keygen "Lays Chips"`  
   `python -m chainofproduct.cli keygen "Auditor Corp"`
4. Run demos:  
   `python clients/seller_client.py` then `python clients/buyer_client.py` then `python clients/third_party_client.py`

### VM2: Application + Group Server (DMZ)
1. Install deps: `pip install -r requirements.txt`
2. Set database connection:  
   `export DATABASE_URL=postgresql://<DB_USER>:<DB_PASS>@<VM3_IP>:5432/chainofproduct`
3. Start servers bound to all interfaces:  
   `python -c "from app.main import start_server; start_server(host='0.0.0.0', port=8001)"`  
   `python -c "from groupserver.main import start_server; start_server(host='0.0.0.0', port=8002)"`
4. Ensure firewall allows inbound from VM1 on 8001/8002 and outbound to VM3:5432.

### VM3: Database Server
1. Install and run PostgreSQL listening on `0.0.0.0:5432` (or chosen port).
2. Create DB/user and grant privileges (see `scripts/setup_vm3_db.sh`).
3. Firewall: allow inbound only from VM2 on DB port.

## TLS Configuration

### Generate Self-Signed Certificates (Testing)

```bash
# For VM2 (Application Server)
openssl req -x509 -newkey rsa:4096 -keyout app_key.pem -out app_cert.pem -days 365 -nodes

# For VM2 (Group Server) - can reuse app cert or generate separate
openssl req -x509 -newkey rsa:4096 -keyout group_key.pem -out group_cert.pem -days 365 -nodes
```

### Update Server Startup (Production)

```python
# app/main.py
if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8001,
        ssl_keyfile="app_key.pem",
        ssl_certfile="app_cert.pem"
    )
```

## Usage

### CLI Commands

```bash
# Generate keys for a company
python -m chainofproduct.cli keygen "Company Name"

# Protect a transaction
python -m chainofproduct.cli protect input.json output.protected.json \
  --recipients "Company1,Company2" \
  --groups "group1,group2"

# Verify a protected document
python -m chainofproduct.cli check protected.json

# Decrypt a protected document
python -m chainofproduct.cli unprotect protected.json "Company Name" output.json

# Add buyer signature
python -m chainofproduct.cli buyer-sign protected.json "Buyer Name" signed.json
```

### Complete Demo Workflow

**1. Start servers (separate terminals):**

```bash
# Terminal 1: Group Server (VM4)
python -m groupserver.main

# Terminal 2: Application Server (VM2/DMZ)
python -m app.main
```

**2. Setup groups and companies:**

```bash
# Create a partner group
curl -X POST http://localhost:8002/groups/create \
  -H "Content-Type: application/json" \
  -d '{"group_id": "tech_partners", "members": ["Auditor Corp"]}'
```

**3. Run seller client:**

```bash
python clients/seller_client.py
```

This will:
- ✓ Register seller company
- ✓ Generate and protect transaction
- ✓ Upload encrypted transaction to server
- ✓ Demonstrate SR1 (Confidentiality) - server never sees plaintext

**4. Run buyer client:**

```bash
python clients/buyer_client.py
```

This will:
- ✓ Register buyer company
- ✓ Retrieve and verify transaction (SR2, SR3)
- ✓ Decrypt and review transaction
- ✓ Add buyer signature
- ✓ Share with auditor and group
- ✓ Create auditable share records (SR4)

**5. Run third-party client:**

```bash
python clients/third_party_client.py
```

This will:
- ✓ Register third party
- ✓ Access as authorized party (Auditor Corp) - succeeds
- ✓ Access as unauthorized party (Random Company) - fails
- ✓ Demonstrate SR1 enforcement
- ✓ Audit share records (SR4)

## API Endpoints

### Application Server (VM2 - Port 8001)

#### Company Management
- `POST /register_company` - Register company with public keys
- `GET /companies` - List all companies
- `GET /companies/{company_name}` - Get company public keys

#### Transaction Management
- `POST /transactions` - Store protected transaction
- `GET /transactions/{tx_id}` - Retrieve transaction
- `POST /transactions/{tx_id}/buyer_sign` - Add buyer signature

#### Share Management
- `POST /transactions/{tx_id}/share` - Record individual share
- `POST /transactions/{tx_id}/share_group` - Record group share
- `GET /transactions/{tx_id}/shares` - Get individual share records
- `GET /transactions/{tx_id}/group_shares` - Get group share records

### Group Server (VM4 - Port 8002)

- `POST /groups/create` - Create new group
- `POST /groups/{group_id}/add_member` - Add member to group
- `POST /groups/{group_id}/remove_member` - Remove member from group
- `GET /groups/{group_id}/members` - Get current members
- `GET /groups/{group_id}` - Get group info
- `GET /groups` - List all groups

## Security Requirements Verification

### SR1: Confidentiality
✓ **Implementation**: AES-256-GCM encryption with unique per-transaction keys
✓ **Verification**: Run third_party_client.py - unauthorized parties cannot decrypt

### SR2: Authentication
✓ **Implementation**: Ed25519 signatures from seller and buyer
✓ **Verification**: CLI `check` command verifies signatures

### SR3: Integrity 1
✓ **Implementation**: AES-GCM provides authenticated encryption
✓ **Verification**: Tampering with ciphertext causes decryption failure

### SR4: Integrity 2
✓ **Implementation**: Signed share records stored on server
✓ **Verification**: Seller can query share records to audit disclosures

### Dynamic Groups
✓ **Implementation**: 
  - Group keys derived from transaction key + group ID + transaction ID
  - Keys wrapped only for current members at disclosure time
  - New members don't get old keys
  - Removed members can't decrypt future transactions

✓ **Verification**:
  - Add member after transaction disclosure - cannot decrypt
  - Remove member - cannot decrypt new transactions

## Cryptographic Design

### Key Hierarchy

```
Identity Keys (per company):
├── Signing: Ed25519 (ssk, spk)
└── Encryption: X25519 (sk, pk)

Transaction Keys:
├── K_T: AES-256 key (random)
├── Individual wrapping: Enc(pk_recipient, K_T) using X25519+HKDF
└── Group wrapping:
    ├── GroupKey_G_T = HKDF(K_T, GroupID, TxID)
    └── For each member M: Enc(pk_M, GroupKey_G_T)
```

### Signatures

```
Seller signs: Sign(ssk_seller, SHA256(transaction))
Buyer signs: Sign(ssk_buyer, SHA256(transaction))
Share record: Sign(ssk_sharer, SHA256(share_record))
```

### No Custom Crypto
All primitives from Python `cryptography` library:
- Ed25519 for signatures (RFC 8032)
- X25519 for key exchange (RFC 7748)
- AES-256-GCM for encryption (NIST SP 800-38D)
- HKDF for key derivation (RFC 5869)
- SHA-256 for hashing (FIPS 180-4)

## Testing

### Unit Tests (Not Included - Add as needed)

```python
# Test cryptographic operations
pytest tests/test_crypto.py

# Test library functions
pytest tests/test_library.py

# Test servers
pytest tests/test_app.py
pytest tests/test_groupserver.py
```

### Integration Testing

Run the complete demo workflow described above to verify all security requirements.

## Production Considerations

1. **Key Storage**: Use HSM or secure key management service
2. **Database**: Migrate from SQLite to PostgreSQL/MySQL
3. **TLS**: Use proper CA-signed certificates
4. **Authentication**: Add OAuth2/JWT for API access
5. **Rate Limiting**: Implement rate limiting on all endpoints
6. **Logging**: Add comprehensive audit logging
7. **Monitoring**: Set up alerting for security events
8. **Backup**: Regular encrypted backups of database
9. **Key Rotation**: Implement key rotation policies
10. **Network**: Use VPCs and security groups in cloud deployments

## Troubleshooting

### Common Issues

**"Public key not found for X"**
- Run `python -m chainofproduct.cli keygen "Company Name"`
- Ensure all parties have registered with application server

**"Connection refused to server"**
- Verify servers are running: `curl http://localhost:8001`
- Check firewall rules
- Verify correct ports (8001 for app, 8002 for groups)

**"Decryption failed"**
- Verify you're listed in recipients or group members
- Check transaction was properly protected
- Ensure keys match (re-register if needed)

## License

[Add your license here]

## Contributors

[Add contributors here]

## References

- [RFC 8032 - Ed25519](https://tools.ietf.org/html/rfc8032)
- [RFC 7748 - X25519](https://tools.ietf.org/html/rfc7748)
- [RFC 5869 - HKDF](https://tools.ietf.org/html/rfc5869)
- [NIST SP 800-38D - GCM](https://csrc.nist.gov/publications/detail/sp/800-38d/final)
