"""Auth routes: token issuance."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import create_access_token, verify_password
from database import get_conn
from schemas import TokenRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def login(body: TokenRequest, request: Request):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT username, password_hash, role FROM users WHERE username=?", (body.username,))
    row = cur.fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect username or password"},
        )

    # Update last login
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cur.execute("UPDATE users SET last_login=? WHERE username=?", (now, body.username))
    conn.commit()
    conn.close()

    token = create_access_token(username=row["username"], role=row["role"])
    return TokenResponse(access_token=token, role=row["role"], username=row["username"])
