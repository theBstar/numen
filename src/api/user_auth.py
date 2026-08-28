"""User authentication via Google OAuth + JWT tokens."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import ensure_person_entity_for_member, get_db
from src.api.rate_limit import limiter
from src.api.signup_policy import may_create_org, may_join_domain_org
from src.config import settings
from src.shared.audit import log_action_safely
from src.shared.models import Organization, OrgMember, User
from src.shared.types import RoleType

logger = logging.getLogger(__name__)

PERSONAL_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "yahoo.com",
    "outlook.com",
    "icloud.com",
    "protonmail.com",
    "aol.com",
    "live.com",
    "me.com",
    "mail.com",
}


def is_business_email(email: str) -> bool:
    domain = email.split("@")[1].lower()
    return domain not in PERSONAL_DOMAINS


def get_email_domain(email: str) -> str:
    return email.split("@")[1].lower()


def domain_to_org_name(domain: str) -> str:
    name = domain.split(".")[0]
    return name.replace("-", " ").replace("_", " ").title()


user_auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response models ────────────────────────────────────────


class GoogleAuthUrlRequest(BaseModel):
    redirect_uri: str
    state: str = "/"


class GoogleAuthUrlResponse(BaseModel):
    authorization_url: str


class GoogleLoginRequest(BaseModel):
    code: str
    redirect_uri: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict
    needs_onboarding: bool = False
    orgs: list[dict] = Field(default_factory=list)


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Token utilities ──────────────────────────────────────────────────


def create_access_token(user_id: UUID, email: str) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    """Create a long-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "iat": time.time(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _hash_token(token: str) -> str:
    """SHA-256 hash a token for safe storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Routes ───────────────────────────────────────────────────────────


@user_auth_router.post("/google/auth-url", response_model=GoogleAuthUrlResponse, summary="Get Google OAuth URL")
async def get_google_auth_url(req: GoogleAuthUrlRequest):
    """Generate the Google OAuth consent screen URL. Frontend redirects the user here."""
    from urllib.parse import urlencode

    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    params = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": req.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "consent",
            "state": req.state,
        }
    )
    return GoogleAuthUrlResponse(authorization_url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@user_auth_router.post("/google/login", response_model=TokenResponse, summary="Login via Google OAuth")
@limiter.limit("10/minute")
async def google_login(request: Request, req: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    """Exchange Google OAuth authorization code for JWT access + refresh tokens."""
    ip_address = request.client.host if request.client else None

    # Exchange code for Google tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": req.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": req.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            logger.warning("Google token exchange failed with status %d", resp.status_code)
            await log_action_safely(
                db,
                action="auth.login.failure",
                ip_address=ip_address,
                details={"provider": "google", "reason": "token_exchange_failed", "status": resp.status_code},
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="Failed to exchange Google auth code")
        google_tokens = resp.json()

    # Get user info from Google
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {google_tokens['access_token']}"},
        )
        if resp.status_code != 200:
            logger.warning("Google userinfo request failed with status %d", resp.status_code)
            await log_action_safely(
                db,
                action="auth.login.failure",
                ip_address=ip_address,
                details={"provider": "google", "reason": "userinfo_failed", "status": resp.status_code},
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="Failed to get Google user info")
        user_info = resp.json()

    email = user_info["email"]
    google_id = user_info["id"]
    display_name = user_info.get("name", email.split("@")[0])
    avatar_url = user_info.get("picture")

    # Find or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            google_id=google_id,
            avatar_url=avatar_url,
        )
        db.add(user)
        await db.flush()
    else:
        user.google_id = google_id
        user.display_name = display_name or user.display_name
        user.avatar_url = avatar_url or user.avatar_url
        await db.flush()

    # Create tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    # Store hashed refresh token
    user.hashed_refresh_token = _hash_token(refresh_token)

    # Check admin status
    is_admin_user = email.lower() in settings.get_admin_emails()

    # For admin: ensure membership in demo org
    if is_admin_user:
        demo_result = await db.execute(select(Organization).where(Organization.is_demo.is_(True)))
        demo_orgs = list(demo_result.scalars().all())
        for demo_org in demo_orgs:
            existing = await db.execute(
                select(OrgMember).where(OrgMember.org_id == demo_org.id, OrgMember.email == email)
            )
            if not existing.scalar_one_or_none():
                demo_member = OrgMember(
                    org_id=demo_org.id,
                    user_id=user.id,
                    email=email,
                    display_name=display_name,
                    role=RoleType.CTO,
                )
                db.add(demo_member)
                await db.flush()
                await ensure_person_entity_for_member(db, demo_member)

    # For business email: join the domain's org, and create it if policy allows
    needs_onboarding = False
    if is_business_email(email) and may_join_domain_org(email, settings):
        domain = get_email_domain(email)
        result = await db.execute(select(Organization).where(Organization.domain == domain))
        domain_org = result.scalar_one_or_none()
        if domain_org:
            # Check if already a member
            existing = await db.execute(
                select(OrgMember).where(OrgMember.org_id == domain_org.id, OrgMember.email == email)
            )
            if not existing.scalar_one_or_none():
                domain_member = OrgMember(
                    org_id=domain_org.id,
                    user_id=user.id,
                    email=email,
                    display_name=display_name,
                    role=RoleType.ENGINEER,
                )
                db.add(domain_member)
                await db.flush()
                await ensure_person_entity_for_member(db, domain_member)
        elif may_create_org(email, settings):
            # Create org from domain
            org_name = domain_to_org_name(domain)
            slug = domain.replace(".", "-")
            domain_org = Organization(name=org_name, slug=slug, domain=domain)
            db.add(domain_org)
            await db.flush()
            new_domain_member = OrgMember(
                org_id=domain_org.id,
                user_id=user.id,
                email=email,
                display_name=display_name,
                role=RoleType.ENGINEER,
            )
            db.add(new_domain_member)
            await db.flush()
            await ensure_person_entity_for_member(db, new_domain_member)
        else:
            # Policy allows joining but not creating, and there is no org for
            # this domain yet. Someone has to add them.
            needs_onboarding = True
    else:
        # A personal address, or a business one this instance's signup policy
        # does not admit automatically. Either way they are in only if someone
        # already added them as a member.
        member_result = await db.execute(
            select(OrgMember)
            .where(OrgMember.email == email)
            .where(OrgMember.org_id.notin_(select(Organization.id).where(Organization.is_demo.is_(True))))
        )
        if not list(member_result.scalars().all()):
            needs_onboarding = True

    # Fetch user's orgs
    org_result = await db.execute(
        select(Organization).join(OrgMember, OrgMember.org_id == Organization.id).where(OrgMember.email == email)
    )
    user_orgs = [
        {"id": str(o.id), "name": o.name, "slug": o.slug, "is_demo": o.is_demo} for o in org_result.scalars().all()
    ]

    await log_action_safely(
        db,
        user_id=user.id,
        action="auth.login.success",
        ip_address=ip_address,
        details={
            "provider": "google",
            "is_admin": is_admin_user,
            "needs_onboarding": needs_onboarding,
            "org_count": len(user_orgs),
        },
    )

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "is_admin": is_admin_user,
        },
        needs_onboarding=needs_onboarding,
        orgs=user_orgs,
    )


@user_auth_router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
@limiter.limit("10/minute")
async def refresh_token_endpoint(request: Request, req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for new access + refresh tokens (rotation)."""
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Verify refresh token matches stored hash (detects reuse after rotation)
    if user.hashed_refresh_token != _hash_token(req.refresh_token):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    # Rotate tokens
    new_access = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id)
    user.hashed_refresh_token = _hash_token(new_refresh)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        },
    )


@user_auth_router.post("/logout", summary="Logout and invalidate refresh token")
async def logout(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Invalidate the refresh token so it cannot be reused."""
    try:
        payload = decode_token(req.refresh_token)
        user_id = payload["sub"]
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.hashed_refresh_token = None
            await db.commit()
    except Exception:
        pass  # Logout should always succeed from the caller's perspective
    return {"status": "ok"}
