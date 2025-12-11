# ChainOfProduct - Deployment Guide

PostgreSQL on VM3 is required. VM2 (app + group) connects to VM3; VM1 runs the clients.

## Architecture Overview

```
VM1 (192.168.1.10) - Client
    ↓ HTTP:8001, HTTP:8002
VM2 (192.168.1.20) - Application Server + Group Server
    ↓ PostgreSQL:5432
VM3 (192.168.1.30) - Database Server (Postgres)
```

## Prerequisites

- 3 Kali Linux VMs with network connectivity
- Static IP addresses configured
- Root/sudo access on all VMs
- Internet connection for initial setup
- If you only have 3 physical/host machines, this layout is already 3 nodes: App+Group on VM2, DB on VM3, Clients on VM1 (or your laptop).

### Configure Static IPs on Kali (NetworkManager)
The setup scripts can configure static IPs automatically via `nmcli` when you pass:
- `STATIC_IP_CIDR` (e.g., `192.168.1.10/24`)
- `GATEWAY_IP` (e.g., `192.168.1.1`)
- `DNS_SERVERS` (default `8.8.8.8 1.1.1.1`)
- `CON_NAME` (default `"Wired connection 1"`)
Manual example (if you prefer to run yourself):
```bash
nmcli con show              # list connections (e.g., "Wired connection 1")
nmcli dev status            # see device (e.g., eth0)
nmcli con mod "Wired connection 1" ipv4.addresses 192.168.1.10/24
nmcli con mod "Wired connection 1" ipv4.gateway 192.168.1.1
nmcli con mod "Wired connection 1" ipv4.dns "8.8.8.8 1.1.1.1"
nmcli con mod "Wired connection 1" ipv4.method manual
nmcli con up "Wired connection 1"
```
Suggested layout (adjust to your LAN):
- VM1 (Client): 192.168.1.10
- VM2 (App + Group): 192.168.1.20
- VM3 (DB): 192.168.1.30

---

## STEP 1: VM3 Setup (Database Server - Postgres)

### 1.1 Install PostgreSQL (scripted)
Recommended: run the helper script (sets static IP if provided, installs Postgres, configures pg_hba):
```bash
# On VM3
cd ~/chainofproduct   # after cloning repo
STATIC_IP_CIDR=192.168.1.30/24 GATEWAY_IP=192.168.1.1 \
APP_VM_IP=192.168.1.20 DB_PASSWORD='Y0urStr0ngP@ssw0rd!' \
scripts/setup_vm3_db.sh
```

Manual steps (if you prefer):

```bash
# SSH into VM3
ssh kali@192.168.1.30

# Update system
sudo apt update && sudo apt upgrade -y

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Check PostgreSQL is running
sudo systemctl status postgresql
```

### 1.2 Configure PostgreSQL

```bash
# Find PostgreSQL version
PG_VERSION=$(ls /etc/postgresql/)
echo "PostgreSQL version: $PG_VERSION"

# Configure to listen on all interfaces
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" \
    /etc/postgresql/$PG_VERSION/main/postgresql.conf

# Backup original pg_hba.conf
sudo cp /etc/postgresql/$PG_VERSION/main/pg_hba.conf \
        /etc/postgresql/$PG_VERSION/main/pg_hba.conf.backup

# Configure authentication - ONLY allow VM2
sudo tee -a /etc/postgresql/$PG_VERSION/main/pg_hba.conf << 'EOF'

# ChainOfProduct configuration
# Allow VM2 (Application Server) ONLY
host    all             all             192.168.1.20/32         md5

# Explicitly deny all other connections
host    all             all             0.0.0.0/0               reject
host    all             all             ::/0                    reject
EOF

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### 1.3 Create Database and User

```bash
# Create database and user
sudo -u postgres psql << 'EOF'
-- Create database
CREATE DATABASE chainofproduct;

-- Create user with strong password
CREATE USER copuser WITH PASSWORD 'Y0urStr0ngP@ssw0rd!2024';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE chainofproduct TO copuser;

-- Connect to database and grant schema privileges
\c chainofproduct
GRANT ALL ON SCHEMA public TO copuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO copuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO copuser;

-- Verify
\du
\l

EOF
```

### 1.4 Apply Firewall Rules

```bash
# Create firewall script
cat > ~/vm3_firewall.sh << 'FWEOF'
#!/bin/bash
echo "Applying VM3 (Database) firewall rules..."

# Flush rules
sudo iptables -F
sudo iptables -X
sudo iptables -t nat -F

# Default DROP
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT DROP

# Loopback
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A OUTPUT -o lo -j ACCEPT

# Established connections
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# DNS
sudo iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# PostgreSQL - ONLY from VM2
sudo iptables -A INPUT -p tcp -s 192.168.1.20 --dport 5432 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 5432 -j DROP

# SSH for management
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT

# HTTPS for updates
sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT

# Logging
sudo iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "VM3-INPUT-DROP: " --log-level 4
sudo iptables -A OUTPUT -m limit --limit 5/min -j LOG --log-prefix "VM3-OUTPUT-DROP: " --log-level 4

# Save rules
sudo mkdir -p /etc/iptables
sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null

echo "✓ VM3 firewall rules applied"
sudo iptables -L -v -n
FWEOF

chmod +x ~/vm3_firewall.sh
sudo ~/vm3_firewall.sh
```

### 1.5 Test Database

```bash
# Test local connection
sudo -u postgres psql chainofproduct -c "SELECT version();"

# Check PostgreSQL is listening
sudo netstat -tlnp | grep 5432
# Should show: 0.0.0.0:5432

echo "✓ VM3 Database Server setup complete"
echo "Connection string: postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct"
```

---

## STEP 2: VM2 Setup (Application + Group Server)

### 2.1 Install Dependencies (scripted)
Recommended: use the helper script (can also set static IP):
```bash
# On VM2
cd ~
REPO_URL=<your-github-repo-url> \
STATIC_IP_CIDR=192.168.1.20/24 GATEWAY_IP=192.168.1.1 \
DATABASE_URL=postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct \
scripts/setup_vm2_app_group.sh
```

Manual steps (if you prefer):

```bash
# SSH into VM2
ssh kali@192.168.1.20

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3 python3-pip python3-venv postgresql-client git

# Install Python packages
pip3 install --user cryptography fastapi uvicorn[standard] pydantic psycopg2-binary
```

### 2.2 Clone Project

```bash
# Clone from GitHub (replace URL with your repo)
cd ~
git clone <your-github-repo-url> chainofproduct
cd ~/chainofproduct
```

### 2.3 Configure Database Connection

```bash
# Create environment file
cat > ~/chainofproduct/.env << 'EOF'
DATABASE_URL=postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct
EOF

# Load environment variables
echo "export DATABASE_URL='postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct'" >> ~/.bashrc
source ~/.bashrc
```

### 2.4 Test Database Connection

```bash
# Test PostgreSQL connection from VM2
psql "$DATABASE_URL" -c "SELECT 1 AS test;"

# Should return:
#  test
# ------
#     1
# (1 row)

# If this fails, check:
# 1. VM3 PostgreSQL is running: sudo systemctl status postgresql
# 2. VM3 firewall allows VM2: sudo iptables -L -v -n
# 3. Credentials are correct
```

### 2.5 Apply Firewall Rules

```bash
# Create firewall script
cat > ~/vm2_firewall.sh << 'FWEOF'
#!/bin/bash
echo "Applying VM2 (Application + Group Server) firewall rules..."

# Flush rules
sudo iptables -F
sudo iptables -X
sudo iptables -t nat -F

# Default DROP
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT DROP

# Loopback
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A OUTPUT -o lo -j ACCEPT

# Established connections
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# DNS
sudo iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Application Server - Allow from VM1
sudo iptables -A INPUT -p tcp -s 192.168.1.10 --dport 8001 -j ACCEPT

# Group Server - Allow from VM1
sudo iptables -A INPUT -p tcp -s 192.168.1.10 --dport 8002 -j ACCEPT

# PostgreSQL to VM3
sudo iptables -A OUTPUT -p tcp -d 192.168.1.30 --dport 5432 -j ACCEPT

# SSH
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT

# HTTPS for updates
sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT

# Logging
sudo iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "VM2-INPUT-DROP: " --log-level 4
sudo iptables -A OUTPUT -m limit --limit 5/min -j LOG --log-prefix "VM2-OUTPUT-DROP: " --log-level 4

# Save rules
sudo mkdir -p /etc/iptables
sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null

echo "✓ VM2 firewall rules applied"
sudo iptables -L -v -n
FWEOF

chmod +x ~/vm2_firewall.sh
sudo ~/vm2_firewall.sh
```

### 2.6 Create Systemd Services

```bash
# Application Server Service
sudo tee /etc/systemd/system/cop-app.service << 'EOF'
[Unit]
Description=ChainOfProduct Application Server
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=kali
WorkingDirectory=/home/kali/chainofproduct
Environment="DATABASE_URL=postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct"
Environment="PYTHONPATH=/home/kali/chainofproduct"
ExecStart=/home/kali/.local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Group Server Service
sudo tee /etc/systemd/system/cop-group.service << 'EOF'
[Unit]
Description=ChainOfProduct Group Server
After=network.target postgresql.service cop-app.service
Wants=postgresql.service

[Service]
Type=simple
User=kali
WorkingDirectory=/home/kali/chainofproduct
Environment="DATABASE_URL=postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct"
Environment="PYTHONPATH=/home/kali/chainofproduct"
ExecStart=/home/kali/.local/bin/uvicorn groupserver.main:app --host 0.0.0.0 --port 8002
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload
```

### 2.7 Start Services

```bash
# Enable services to start on boot
sudo systemctl enable cop-app cop-group

# Start services
sudo systemctl start cop-app
sudo systemctl start cop-group

# Check status
sudo systemctl status cop-app
sudo systemctl status cop-group

# View logs
sudo journalctl -u cop-app -f &
sudo journalctl -u cop-group -f &

# Test endpoints
curl http://localhost:8001/
curl http://localhost:8002/
```

---

## STEP 3: VM1 Setup (Client)

### 3.1 Install Dependencies (scripted)
Recommended: use the helper script (can also set static IP):
```bash
# On VM1
cd ~
REPO_URL=<your-github-repo-url> \
STATIC_IP_CIDR=192.168.1.10/24 GATEWAY_IP=192.168.1.1 \
APP_SERVER_URL=http://192.168.1.20:8001 GROUP_SERVER_URL=http://192.168.1.20:8002 \
scripts/setup_vm1_client.sh
```

Manual steps (if you prefer):

```bash
# SSH into VM1
ssh kali@192.168.1.10

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3 python3-pip git

# Install Python packages
pip3 install --user cryptography requests
```

### 3.2 Setup Project Structure

```bash
# Clone from GitHub (replace URL with your repo)
cd ~
git clone <your-github-repo-url> chainofproduct
cd ~/chainofproduct
```

### 3.3 Configure Environment

```bash
# Create environment file
cat > ~/chainofproduct/.env << 'EOF'
export APP_SERVER_URL="http://192.168.1.20:8001"
export GROUP_SERVER_URL="http://192.168.1.20:8002"
export PYTHONPATH="/home/kali/chainofproduct"
EOF

# Load environment
echo "source ~/chainofproduct/.env" >> ~/.bashrc
source ~/.bashrc
```

### 3.4 Apply Firewall Rules

```bash
# Create firewall script
cat > ~/vm1_firewall.sh << 'FWEOF'
#!/bin/bash
echo "Applying VM1 (Client) firewall rules..."

# Flush rules
sudo iptables -F
sudo iptables -X
sudo iptables -t nat -F

# Default DROP
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT DROP

# Loopback
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A OUTPUT -o lo -j ACCEPT

# Established connections
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# DNS
sudo iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Application Server on VM2
sudo iptables -A OUTPUT -p tcp -d 192.168.1.20 --dport 8001 -j ACCEPT

# Group Server on VM2
sudo iptables -A OUTPUT -p tcp -d 192.168.1.20 --dport 8002 -j ACCEPT

# SSH
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT

# HTTPS for updates
sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT

# Logging
sudo iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "VM1-INPUT-DROP: " --log-level 4
sudo iptables -A OUTPUT -m limit --limit 5/min -j LOG --log-prefix "VM1-OUTPUT-DROP: " --log-level 4

# Save rules
sudo mkdir -p /etc/iptables
sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null

echo "✓ VM1 firewall rules applied"
sudo iptables -L -v -n
FWEOF

chmod +x ~/vm1_firewall.sh
sudo ~/vm1_firewall.sh
```

### 3.5 Test Connectivity

```bash
# Test Application Server
curl $APP_SERVER_URL/
# Expected: {"service": "ChainOfProduct Application Server", ...}

# Test Group Server
curl $GROUP_SERVER_URL/
# Expected: {"service": "ChainOfProduct Group Server", ...}

# Test database is NOT accessible (should fail/timeout)
nc -zv 192.168.1.30 5432
# Expected: Connection refused or timeout

echo "✓ VM1 Client setup complete"
```

---

## STEP 4: Run Demo

### 4.1 Generate Keys

```bash
# On VM1
cd ~/chainofproduct

# Generate keys for all parties
python3 -m chainofproduct.cli keygen "Ching Chong Extractions"
python3 -m chainofproduct.cli keygen "Lays Chips"
python3 -m chainofproduct.cli keygen "Auditor Corp"
python3 -m chainofproduct.cli keygen "Random Company"

# Verify keys were created
ls -la ~/chainofproduct/keys/
```

### 4.2 Create Groups

```bash
# Create tech partners group
curl -X POST $GROUP_SERVER_URL/groups/create \
  -H "Content-Type: application/json" \
  -d '{"group_id": "tech_partners", "members": ["Auditor Corp"]}'

# Verify group was created
curl $GROUP_SERVER_URL/groups/tech_partners
```

### 4.3 Run Client Scripts

```bash
# Terminal 1: Run seller client
cd ~/chainofproduct
python3 clients/seller_client.py

# Terminal 2: Run buyer client
cd ~/chainofproduct
python3 clients/buyer_client.py

# Terminal 3: Run third-party client
cd ~/chainofproduct
python3 clients/third_party_client.py
```

---

## Verification Checklist

### Network Security Tests

```bash
# From VM1: Try to access database (should FAIL)
nc -zv 192.168.1.30 5432
# Expected: Timeout or connection refused

# From VM1: Access application server (should SUCCEED)
curl http://192.168.1.20:8001/
# Expected: JSON response

# From VM1: Access group server (should SUCCEED)
curl http://192.168.1.20:8002/
# Expected: JSON response

# From VM2: Access database (should SUCCEED)
psql "$DATABASE_URL" -c "SELECT 1;"
# Expected: Result returned

# From VM3: Try to access application server (should FAIL)
curl http://192.168.1.20:8001/
# Expected: Timeout or connection refused
```

### Firewall Verification

```bash
# On each VM, check rules
sudo iptables -L -v -n

# Check DROP logs
sudo tail -f /var/log/kern.log | grep DROP
```

### Service Health

```bash
# On VM2: Check services
sudo systemctl status cop-app
sudo systemctl status cop-group

# On VM3: Check PostgreSQL
sudo systemctl status postgresql

# Check PostgreSQL connections (on VM3)
sudo -u postgres psql -c "SELECT client_addr, count(*) FROM pg_stat_activity WHERE client_addr IS NOT NULL GROUP BY client_addr;"
# Should only show 192.168.1.20
```

---

## Troubleshooting

### Database Connection Issues

```bash
# On VM3: Check PostgreSQL is listening
sudo netstat -tlnp | grep 5432

# Check pg_hba.conf
sudo cat /etc/postgresql/*/main/pg_hba.conf | grep -v "^#"

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*-main.log

# Test from VM2
psql "postgresql://copuser:Y0urStr0ngP@ssw0rd!2024@192.168.1.30:5432/chainofproduct" -c "SELECT version();"
```

### Firewall Issues

```bash
# Temporarily disable firewall for testing (DO NOT use in production)
sudo iptables -P INPUT ACCEPT
sudo iptables -P OUTPUT ACCEPT
sudo iptables -F

# Re-apply rules
sudo ~/vm<X>_firewall.sh
```

### Service Issues

```bash
# On VM2: Restart services
sudo systemctl restart cop-app cop-group

# View detailed logs
sudo journalctl -u cop-app --since "5 minutes ago"
sudo journalctl -u cop-group --since "5 minutes ago"

# Check if ports are listening
sudo netstat -tlnp | grep -E '8001|8002'
```

---

## Success Criteria

✅ VM3 database only accepts connections from VM2
✅ VM1 can access both services on VM2
✅ VM1 cannot access VM3 database directly
✅ All cryptographic operations work correctly
✅ SR1-SR4 requirements verified
✅ Group disclosure working
✅ Firewall logs show blocked attempts

## Next Steps

1. Configure TLS/SSL for production
2. Set up automated backups
3. Implement monitoring (Prometheus, Grafana)
4. Add rate limiting
5. Configure log rotation
6. Set up alerting for security events
