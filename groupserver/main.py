"""
groupserver/main.py
Group Server - Runs on VM2 alongside Application Server
Uses same PostgreSQL database on VM3
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import uvicorn
import sys
from pathlib import Path

# Add parent directory to path to import db module
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import Database

app = FastAPI(
    title="ChainOfProduct Group Server",
    description="Dynamic group membership management",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection (shared with application server, connects to VM3)
db = Database()


class GroupCreate(BaseModel):
    """Create group request"""
    group_id: str
    members: List[str] = []


class MemberAdd(BaseModel):
    """Add member request"""
    member: str


class MemberRemove(BaseModel):
    """Remove member request"""
    member: str


@app.get("/")
def root():
    """Health check"""
    return {
        "service": "ChainOfProduct Group Server",
        "status": "operational",
        "version": "1.0.0",
        "database": "PostgreSQL on VM3"
    }


@app.post("/groups/create", status_code=status.HTTP_201_CREATED)
def create_group(group: GroupCreate):
    """Create a new partner group"""
    try:
        # Check if group already exists
        if db.group_exists(group.group_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Group {group.group_id} already exists"
            )
        
        # Create group
        group_db_id = db.create_group(group.group_id)
        
        # Add initial members
        for member in group.members:
            try:
                db.add_group_member(group.group_id, member)
            except Exception as e:
                print(f"Warning: Could not add member {member}: {e}")
        
        return {
            "id": group_db_id,
            "group_id": group.group_id,
            "members": group.members,
            "message": "Group created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create group: {str(e)}"
        )


@app.post("/groups/{group_id}/add_member")
def add_member(group_id: str, member: MemberAdd):
    """Add a member to a group"""
    try:
        # Check if group exists
        if not db.group_exists(group_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        # Add member
        try:
            member_id = db.add_group_member(group_id, member.member)
            return {
                "id": member_id,
                "group_id": group_id,
                "member": member.member,
                "message": "Member added successfully"
            }
        except Exception as e:
            # Member might already exist
            if "UNIQUE constraint" in str(e) or "duplicate key" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Member {member.member} already in group {group_id}"
                )
            raise
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add member: {str(e)}"
        )


@app.post("/groups/{group_id}/remove_member")
def remove_member(group_id: str, member: MemberRemove):
    """Remove a member from a group"""
    try:
        # Check if group exists
        if not db.group_exists(group_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        # Remove member
        success = db.remove_group_member(group_id, member.member)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {member.member} not found in group {group_id}"
            )
        
        return {
            "group_id": group_id,
            "member": member.member,
            "message": "Member removed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove member: {str(e)}"
        )


@app.get("/groups/{group_id}/members")
def get_members(group_id: str):
    """
    Get all members of a group
    Used by Application Server when processing group disclosures
    """
    try:
        # Check if group exists
        if not db.group_exists(group_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        # Get members
        members = db.get_group_members(group_id)
        
        return {
            "group_id": group_id,
            "members": members,
            "count": len(members)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get members: {str(e)}"
        )


@app.get("/groups/{group_id}")
def get_group(group_id: str):
    """Get group information"""
    try:
        # Check if group exists
        if not db.group_exists(group_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        # Get members
        members = db.get_group_members(group_id)
        
        return {
            "group_id": group_id,
            "members": members,
            "member_count": len(members)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get group: {str(e)}"
        )


@app.get("/groups")
def list_groups():
    """List all groups"""
    try:
        groups = db.list_groups()
        return {
            "groups": groups,
            "count": len(groups)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list groups: {str(e)}"
        )


def start_server(host: str = "0.0.0.0", port: int = 8002):
    """Start the group server"""
    print(f"Starting Group Server on {host}:{port}")
    print(f"Database: PostgreSQL on VM3 (192.168.1.30:5432)")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()