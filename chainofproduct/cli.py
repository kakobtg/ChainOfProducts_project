"""
chainofproduct/cli.py
Command-line interface for ChainOfProduct operations
"""

import sys
import json
import argparse
from pathlib import Path
from .library import protect, check, unprotect, buyer_sign
from .keymanager import KeyManager, PublicKeyStore


def print_error(message: str, details: str = None):
    """Print error message"""
    print(f"ERROR: {message}", file=sys.stderr)
    if details:
        print(f"Details: {details}", file=sys.stderr)


def cmd_protect(args):
    """Protect a transaction"""
    try:
        # Load transaction
        with open(args.input, 'r') as f:
            transaction = json.load(f)
        
        # Initialize key manager and public key store
        key_manager = KeyManager()
        public_key_store = PublicKeyStore()
        
        # Get seller and buyer from transaction
        seller = transaction.get("seller")
        buyer = transaction.get("buyer")
        
        if not seller or not buyer:
            print_error("Transaction must contain 'seller' and 'buyer' fields")
            return 1
        
        # Parse recipients and groups
        recipients = args.recipients.split(',') if args.recipients else []
        groups = args.groups.split(',') if args.groups else []
        
        # Protect transaction
        protected_doc = protect(
            transaction,
            seller,
            buyer,
            key_manager,
            public_key_store,
            recipients=recipients if recipients else None,
            groups=groups if groups else None,
            group_server_url=args.group_server
        )
        
        # Save protected document
        with open(args.output, 'w') as f:
            json.dump(protected_doc, f, indent=2)
        
        print(f"✓ Transaction protected successfully")
        print(f"  Output: {args.output}")
        print(f"  Transaction ID: {protected_doc['transaction_id']}")
        print(f"  Recipients: {len(protected_doc.get('wrapped_keys', {}))} individual")
        print(f"  Groups: {len(protected_doc.get('group_wrapped_keys', {}))} groups")
        
        return 0
        
    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        return 1
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in input file", str(e))
        return 1
    except Exception as e:
        print_error(f"Protection failed", str(e))
        return 1


def cmd_check(args):
    """Check a protected document"""
    try:
        # Load protected document
        with open(args.input, 'r') as f:
            protected_doc = json.load(f)
        
        # Initialize public key store
        public_key_store = PublicKeyStore()
        
        # Check document
        results = check(protected_doc, public_key_store)
        
        # Print results
        if results["valid"]:
            print("✓ Document verification PASSED")
        else:
            print("✗ Document verification FAILED")
        
        print(f"\nDetails:")
        for key, value in results.get("details", {}).items():
            print(f"  {key}: {value}")
        
        if results.get("warnings"):
            print(f"\nWarnings:")
            for warning in results["warnings"]:
                print(f"  - {warning}")
        
        if results.get("errors"):
            print(f"\nErrors:")
            for error in results["errors"]:
                print(f"  - {error}")
        
        return 0 if results["valid"] else 1
        
    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        return 1
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in input file", str(e))
        return 1
    except Exception as e:
        print_error(f"Verification failed", str(e))
        return 1


def cmd_unprotect(args):
    """Unprotect a document"""
    try:
        # Load protected document
        with open(args.input, 'r') as f:
            protected_doc = json.load(f)
        
        # Initialize key manager
        key_manager = KeyManager()
        
        # Unprotect
        result = unprotect(protected_doc, args.company, key_manager)
        
        # Save decrypted transaction
        with open(args.output, 'w') as f:
            json.dump(result["transaction"], f, indent=2)
        
        print(f"✓ Document decrypted successfully")
        print(f"  Output: {args.output}")
        print(f"  Access method: {result['access_method']}")
        print(f"  Transaction ID: {result['transaction']['id']}")
        
        return 0
        
    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        return 1
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in input file", str(e))
        return 1
    except Exception as e:
        print_error(f"Decryption failed", str(e))
        return 1


def cmd_keygen(args):
    """Generate keys for a company"""
    try:
        key_manager = KeyManager()
        public_key_store = PublicKeyStore()
        
        # Generate keys
        public_keys = key_manager.generate_company_keys(args.company)
        
        # Store in public key store
        public_key_store.add_company(public_keys)
        
        print(f"✓ Keys generated for {args.company}")
        print(f"  Private keys stored in: keys/{args.company}/")
        print(f"  Public keys registered in public key store")
        
        return 0
        
    except Exception as e:
        print_error(f"Key generation failed", str(e))
        return 1


def cmd_buyer_sign(args):
    """Add buyer signature to protected document"""
    try:
        # Load protected document
        with open(args.input, 'r') as f:
            protected_doc = json.load(f)
        
        # Initialize key manager
        key_manager = KeyManager()
        
        # Add buyer signature
        updated_doc = buyer_sign(protected_doc, args.buyer, key_manager)
        
        # Save
        with open(args.output, 'w') as f:
            json.dump(updated_doc, f, indent=2)
        
        print(f"✓ Buyer signature added successfully")
        print(f"  Output: {args.output}")
        
        return 0
        
    except Exception as e:
        print_error(f"Signing failed", str(e))
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="ChainOfProduct - Secure Transaction Protection System",
        prog="cop"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Protect command
    protect_parser = subparsers.add_parser('protect', help='Protect a transaction')
    protect_parser.add_argument('input', help='Input transaction JSON file')
    protect_parser.add_argument('output', help='Output protected document file')
    protect_parser.add_argument('--recipients', help='Comma-separated list of additional recipients')
    protect_parser.add_argument('--groups', help='Comma-separated list of group IDs')
    protect_parser.add_argument('--group-server', default='http://localhost:8002',
                               help='Group server URL')
    
    # Check command
    check_parser = subparsers.add_parser('check', help='Verify a protected document')
    check_parser.add_argument('input', help='Protected document file')
    
    # Unprotect command
    unprotect_parser = subparsers.add_parser('unprotect', help='Decrypt a protected document')
    unprotect_parser.add_argument('input', help='Protected document file')
    unprotect_parser.add_argument('company', help='Company name to decrypt as')
    unprotect_parser.add_argument('output', help='Output decrypted transaction file')
    
    # Keygen command
    keygen_parser = subparsers.add_parser('keygen', help='Generate keys for a company')
    keygen_parser.add_argument('company', help='Company name')
    
    # Buyer-sign command
    buyer_sign_parser = subparsers.add_parser('buyer-sign', help='Add buyer signature')
    buyer_sign_parser.add_argument('input', help='Protected document file')
    buyer_sign_parser.add_argument('buyer', help='Buyer company name')
    buyer_sign_parser.add_argument('output', help='Output signed document file')
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Execute command
    if args.command == 'protect':
        return cmd_protect(args)
    elif args.command == 'check':
        return cmd_check(args)
    elif args.command == 'unprotect':
        return cmd_unprotect(args)
    elif args.command == 'keygen':
        return cmd_keygen(args)
    elif args.command == 'buyer-sign':
        return cmd_buyer_sign(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())