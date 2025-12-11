"""
app/db.py
Database operations using PostgreSQL
Runs on VM3 (Database Server), accessed from VM2 only
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool


class Database:
    """Database interface for ChainOfProduct system"""
    
    def __init__(self, db_url: str = None):
        """
        Initialize database connection
        db_url format: postgresql://user:password@host:port/dbname
        """
        self.db_url = db_url or os.getenv('DATABASE_URL',
            'postgresql://copuser:SecurePassword123!@192.168.1.30:5432/chainofproduct')
        # Create connection pool
        self.pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,  # min and max connections
            self.db_url
        )
        print(f"Connected to PostgreSQL database")

        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Companies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    company_name TEXT UNIQUE NOT NULL,
                    signing_public_key TEXT NOT NULL,
                    encryption_public_key TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    transaction_id INTEGER UNIQUE NOT NULL,
                    protected_document TEXT NOT NULL,
                    seller TEXT,
                    buyer TEXT,
                    buyer_signed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Share records table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS share_records (
                    id SERIAL PRIMARY KEY,
                    transaction_id INTEGER NOT NULL,
                    shared_by TEXT NOT NULL,
                    shared_with TEXT NOT NULL,
                    share_type TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
                )
            """)
            
            # Group share records table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_share_records (
                    id SERIAL PRIMARY KEY,
                    transaction_id INTEGER NOT NULL,
                    shared_by TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
                )
            """)
            
            # Groups table (for group server)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id SERIAL PRIMARY KEY,
                    group_id TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Group members table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    id SERIAL PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    member_name TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(group_id, member_name),
                    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            print("Database schema initialized")
    
    def register_company(self, company_name: str, signing_public_key: str,
                        encryption_public_key: str) -> int:
        """Register a new company"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO companies (company_name, signing_public_key, encryption_public_key)
                VALUES (%s, %s, %s) RETURNING id
            """, (company_name, signing_public_key, encryption_public_key))
            return cursor.fetchone()[0]
    
    def get_company(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Get company by name"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM companies WHERE company_name = %s
            """, (company_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def list_companies(self) -> List[Dict[str, Any]]:
        """List all companies"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM companies")
            return [dict(row) for row in cursor.fetchall()]
    
    def create_transaction(self, transaction_id: int, protected_document: Dict[str, Any],
                          seller: str, buyer: str) -> int:
        """Create a new transaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (transaction_id, protected_document, seller, buyer)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (transaction_id, json.dumps(protected_document), seller, buyer))
            return cursor.fetchone()[0]
    
    def get_transaction(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """Get transaction by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM transactions WHERE transaction_id = %s
            """, (transaction_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['protected_document'] = json.loads(result['protected_document'])
                return result
            return None
    
    def update_transaction_buyer_signature(self, transaction_id: int,
                                          protected_document: Dict[str, Any]) -> bool:
        """Update transaction with buyer signature"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE transactions
                SET protected_document = %s, buyer_signed = TRUE
                WHERE transaction_id = %s
            """, (json.dumps(protected_document), transaction_id))
            return cursor.rowcount > 0
    
    def create_share_record(self, transaction_id: int, shared_by: str,
                           shared_with: str, signature: str) -> int:
        """Create a share record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO share_records (transaction_id, shared_by, shared_with,
                                          share_type, signature)
                VALUES (%s, %s, %s, 'individual', %s) RETURNING id
            """, (transaction_id, shared_by, shared_with, signature))
            return cursor.fetchone()[0]
    
    def create_group_share_record(self, transaction_id: int, shared_by: str,
                                  group_id: str, signature: str) -> int:
        """Create a group share record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO group_share_records (transaction_id, shared_by, group_id, signature)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (transaction_id, shared_by, group_id, signature))
            return cursor.fetchone()[0]
    
    def get_share_records(self, transaction_id: int) -> List[Dict[str, Any]]:
        """Get all share records for a transaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM share_records WHERE transaction_id = %s
            """, (transaction_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_group_share_records(self, transaction_id: int) -> List[Dict[str, Any]]:
        """Get all group share records for a transaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT * FROM group_share_records WHERE transaction_id = %s
            """, (transaction_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # Group management methods
    def create_group(self, group_id: str) -> int:
        """Create a new group"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO groups (group_id) VALUES (%s) RETURNING id
            """, (group_id,))
            return cursor.fetchone()[0]
    
    def group_exists(self, group_id: str) -> bool:
        """Check if group exists"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM groups WHERE group_id = %s
            """, (group_id,))
            return cursor.fetchone() is not None
    
    def add_group_member(self, group_id: str, member_name: str) -> int:
        """Add member to group"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO group_members (group_id, member_name)
                VALUES (%s, %s) RETURNING id
            """, (group_id, member_name))
            return cursor.fetchone()[0]
    
    def remove_group_member(self, group_id: str, member_name: str) -> bool:
        """Remove member from group"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM group_members WHERE group_id = %s AND member_name = %s
            """, (group_id, member_name))
            return cursor.rowcount > 0
    
    def get_group_members(self, group_id: str) -> List[str]:
        """Get all members of a group"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT member_name FROM group_members WHERE group_id = %s
            """, (group_id,))
            return [row['member_name'] for row in cursor.fetchall()]
    
    def list_groups(self) -> List[str]:
        """List all group IDs"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT group_id FROM groups")
            return [row['group_id'] for row in cursor.fetchall()]
