"""
Dev Panel API - Test user management and context switching.

IMPORTANT: This router is ONLY enabled in development/local environments.
It provides quick access to:
- List all test personas
- Switch user context (impersonate)
- Toggle permissions on the fly
- View current RBAC context
- Generate test tokens

All endpoints are prefixed with /api/dev/
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.config import get_settings

# Only import if we're in a development environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
IS_DEV = ENVIRONMENT in ("local", "development", "test")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dev", tags=["Dev Panel"])

# =============================================================================
# MODELS
# =============================================================================

class PersonaInfo(BaseModel):
    """Test persona information."""
    id: str
    email: str
    name: str
    description: str
    profile: str | None
    companies: list[str]
    teams: list[dict] = []
    use_for: list[str] = []


class ImpersonateRequest(BaseModel):
    """Request to impersonate a user."""
    persona_id: str


class TogglePermissionRequest(BaseModel):
    """Request to toggle a permission."""
    permission: str
    enabled: bool


class AddPermissionsRequest(BaseModel):
    """Request to add temporary permissions."""
    permissions: list[str]


class RemovePermissionsRequest(BaseModel):
    """Request to remove temporary permissions."""
    permissions: list[str]


class PermissionOverrides(BaseModel):
    """Current permission overrides."""
    added: list[str] = []
    removed: list[str] = []


class ToggleCompanyRequest(BaseModel):
    """Request to toggle a company."""
    company: str
    enabled: bool


class AddCompaniesRequest(BaseModel):
    """Request to add temporary companies."""
    companies: list[str]


class RemoveCompaniesRequest(BaseModel):
    """Request to remove temporary companies."""
    companies: list[str]


class CompanyOverrides(BaseModel):
    """Current company overrides."""
    added: list[str] = []
    removed: list[str] = []


class CurrentContext(BaseModel):
    """Current user context for debugging."""
    user_id: str | None
    email: str | None
    name: str | None
    profile: str | None
    permissions: list[str]
    companies: list[str]
    teams: list[dict]
    is_impersonating: bool = False
    impersonated_persona: str | None = None


# =============================================================================
# HELPERS
# =============================================================================

PERSONAS_FILE = Path(__file__).parent.parent.parent.parent / "shared" / "testing" / "personas.yaml"


def load_personas() -> dict:
    """Load test personas from YAML file."""
    if not PERSONAS_FILE.exists():
        return {"personas": [], "scenarios": {}}
    with open(PERSONAS_FILE) as f:
        return yaml.safe_load(f) or {"personas": [], "scenarios": {}}


def dev_only():
    """Dependency to ensure dev-only access."""
    if not IS_DEV:
        raise HTTPException(
            status_code=403,
            detail="Dev panel is only available in development environments"
        )
    return True


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status")
async def dev_status(_: bool = Depends(dev_only)) -> dict:
    """Check if dev panel is enabled."""
    return {
        "enabled": IS_DEV,
        "environment": ENVIRONMENT,
        "personas_file_exists": PERSONAS_FILE.exists(),
    }


@router.get("/personas", response_model=list[PersonaInfo])
async def list_personas(_: bool = Depends(dev_only)) -> list[PersonaInfo]:
    """List all available test personas."""
    data = load_personas()
    personas = []

    for p in data.get("personas", []):
        personas.append(PersonaInfo(
            id=p["id"],
            email=p["email"],
            name=p["name"],
            description=p.get("description", ""),
            profile=p.get("profile"),
            companies=p.get("companies", []),
            teams=p.get("teams", []),
            use_for=p.get("use_for", []),
        ))

    return personas


@router.get("/personas/{persona_id}", response_model=PersonaInfo)
async def get_persona(persona_id: str, _: bool = Depends(dev_only)) -> PersonaInfo:
    """Get a specific test persona."""
    data = load_personas()

    for p in data.get("personas", []):
        if p["id"] == persona_id:
            return PersonaInfo(
                id=p["id"],
                email=p["email"],
                name=p["name"],
                description=p.get("description", ""),
                profile=p.get("profile"),
                companies=p.get("companies", []),
                teams=p.get("teams", []),
                use_for=p.get("use_for", []),
            )

    raise HTTPException(status_code=404, detail=f"Persona '{persona_id}' not found")


@router.get("/scenarios")
async def list_scenarios(_: bool = Depends(dev_only)) -> dict:
    """List available test scenarios."""
    data = load_personas()
    return data.get("scenarios", {})


@router.post("/impersonate")
async def impersonate_user(
    request: ImpersonateRequest,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Impersonate a test persona.

    Sets a cookie that the RBAC service will use to override the current user context.
    Only works in development environments.
    """
    data = load_personas()
    persona = None

    for p in data.get("personas", []):
        if p["id"] == request.persona_id:
            persona = p
            break

    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{request.persona_id}' not found")

    # Set impersonation cookie
    impersonate_data = json.dumps({
        "persona_id": persona["id"],
        "email": persona["email"],
        "name": persona["name"],
        "profile": persona.get("profile"),
        "companies": persona.get("companies", []),
    })

    response.set_cookie(
        key="dev_impersonate",
        value=impersonate_data,
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,  # 8 hours
    )

    logger.info(f"[DEV] Impersonating persona: {persona['id']} ({persona['email']})")

    return {
        "status": "impersonating",
        "persona": persona["id"],
        "email": persona["email"],
        "profile": persona.get("profile"),
        "companies": persona.get("companies", []),
        "message": f"Now impersonating {persona['name']}. Refresh the page to see changes.",
    }


@router.post("/stop-impersonation")
async def stop_impersonation(
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """Stop impersonating and return to your real user."""
    response.delete_cookie("dev_impersonate")
    return {"status": "stopped", "message": "Impersonation stopped. Refresh to use your real account."}


@router.get("/context", response_model=CurrentContext)
async def get_current_context(
    request: Request,
    _: bool = Depends(dev_only),
) -> CurrentContext:
    """
    Get the current RBAC context for debugging.

    Shows what permissions, companies, and teams the current user has.
    """
    # Check for impersonation cookie
    impersonate_cookie = request.cookies.get("dev_impersonate")
    is_impersonating = False
    impersonated_persona = None

    if impersonate_cookie:
        try:
            impersonate_data = json.loads(impersonate_cookie)
            is_impersonating = True
            impersonated_persona = impersonate_data.get("persona_id")

            # Return impersonated context
            return CurrentContext(
                user_id=f"test-{impersonated_persona}",
                email=impersonate_data.get("email"),
                name=impersonate_data.get("name"),
                profile=impersonate_data.get("profile"),
                permissions=_get_profile_permissions(impersonate_data.get("profile")),
                companies=impersonate_data.get("companies", []),
                teams=[],
                is_impersonating=True,
                impersonated_persona=impersonated_persona,
            )
        except json.JSONDecodeError:
            pass

    # Get real context from request state (set by auth middleware)
    user = getattr(request.state, "user", None)

    if not user:
        return CurrentContext(
            user_id=None,
            email=None,
            name=None,
            profile=None,
            permissions=[],
            companies=[],
            teams=[],
            is_impersonating=False,
            impersonated_persona=None,
        )

    return CurrentContext(
        user_id=getattr(user, "id", None),
        email=getattr(user, "email", None),
        name=getattr(user, "name", None),
        profile=getattr(user, "profile", None),
        permissions=getattr(user, "permissions", []),
        companies=getattr(user, "companies", []),
        teams=getattr(user, "teams", []),
        is_impersonating=False,
        impersonated_persona=None,
    )


@router.get("/permissions")
async def list_all_permissions(_: bool = Depends(dev_only)) -> dict:
    """List all available permissions in the system."""
    # These match the permissions defined in personas.yaml
    permissions = {
        "core": {
            "users": ["read", "create", "update", "delete", "manage"],
            "teams": ["read", "create", "update", "delete", "manage"],
            "profiles": ["read", "create", "update", "delete", "manage"],
            "ai_costs": ["read", "manage"],
            "api": ["access"],
        },
        "sales": {
            "proposals": ["read", "create", "update", "delete", "export", "bulk_update", "bulk_delete"],
            "booking_orders": ["read", "create", "update", "delete"],
            "mockups": ["read", "generate", "setup"],
            "rate_cards": ["read", "update"],
            "reports": ["read", "export"],
            "chat": ["use"],
        },
        "assets": {
            "locations": ["read", "create", "update", "delete"],
            "networks": ["read", "create", "update", "delete"],
            "packages": ["read", "create", "update", "delete"],
            "asset_types": ["read", "create", "update", "delete"],
        },
        "admin": {
            "users": ["read", "manage"],
            "audit": ["read"],
        },
    }

    return permissions


@router.get("/quick-switch")
async def quick_switch_info(_: bool = Depends(dev_only)) -> dict:
    """Get quick switch options for common test scenarios."""
    data = load_personas()
    personas = data.get("personas", [])

    # Group by role for quick switching
    quick_switch = {
        "admins": [],
        "managers": [],
        "sales_reps": [],
        "coordinators": [],
        "finance": [],
        "edge_cases": [],
    }

    for p in personas:
        profile = p.get("profile")
        info = {"id": p["id"], "name": p["name"], "email": p["email"]}

        if profile == "system_admin":
            quick_switch["admins"].append(info)
        elif profile == "sales_manager":
            quick_switch["managers"].append(info)
        elif profile == "sales_rep":
            quick_switch["sales_reps"].append(info)
        elif profile == "coordinator":
            quick_switch["coordinators"].append(info)
        elif profile == "finance":
            quick_switch["finance"].append(info)
        else:
            quick_switch["edge_cases"].append(info)

    return quick_switch


# =============================================================================
# HELPERS
# =============================================================================

def _get_profile_permissions(profile_name: str | None) -> list[str]:
    """Get permissions for a profile from the personas file."""
    if not profile_name:
        return []

    data = load_personas()
    profiles = data.get("profiles", {})
    profile = profiles.get(profile_name, {})

    return profile.get("permissions", [])


# =============================================================================
# MIDDLEWARE HELPER
# =============================================================================

def get_impersonation_context(request: Request) -> dict | None:
    """
    Check if request has impersonation context.

    Use this in your auth middleware to override user context:

    ```python
    from routers.dev_panel import get_impersonation_context

    impersonate = get_impersonation_context(request)
    if impersonate and IS_DEV:
        # Use impersonated context instead of real user
        return create_user_from_impersonation(impersonate)
    ```
    """
    if not IS_DEV:
        return None

    impersonate_cookie = request.cookies.get("dev_impersonate")
    if not impersonate_cookie:
        return None

    try:
        return json.loads(impersonate_cookie)
    except json.JSONDecodeError:
        return None


def get_permission_overrides(request: Request) -> dict:
    """
    Get current permission overrides from cookie.

    Returns dict with 'added' and 'removed' permission lists.
    """
    if not IS_DEV:
        return {"added": [], "removed": []}

    override_cookie = request.cookies.get("dev_permission_overrides")
    if not override_cookie:
        return {"added": [], "removed": []}

    try:
        return json.loads(override_cookie)
    except json.JSONDecodeError:
        return {"added": [], "removed": []}


def get_company_overrides(request: Request) -> dict:
    """
    Get current company overrides from cookie.

    Returns dict with 'added' and 'removed' company lists.
    """
    if not IS_DEV:
        return {"added": [], "removed": []}

    override_cookie = request.cookies.get("dev_company_overrides")
    if not override_cookie:
        return {"added": [], "removed": []}

    try:
        return json.loads(override_cookie)
    except json.JSONDecodeError:
        return {"added": [], "removed": []}


# =============================================================================
# PERMISSION TOGGLE ENDPOINTS
# =============================================================================

@router.post("/permissions/toggle")
async def toggle_permission(
    request_data: TogglePermissionRequest,
    request: Request,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Toggle a single permission on/off for testing.

    - If `enabled=true`: Adds the permission to the user's context
    - If `enabled=false`: Removes the permission from the user's context

    This allows testing specific permission scenarios without changing the persona.
    """
    overrides = get_permission_overrides(request)
    permission = request_data.permission

    if request_data.enabled:
        # Add permission
        if permission not in overrides.get("added", []):
            overrides.setdefault("added", []).append(permission)
        # Remove from 'removed' if present
        if permission in overrides.get("removed", []):
            overrides["removed"].remove(permission)
    else:
        # Remove permission
        if permission not in overrides.get("removed", []):
            overrides.setdefault("removed", []).append(permission)
        # Remove from 'added' if present
        if permission in overrides.get("added", []):
            overrides["added"].remove(permission)

    # Save to cookie
    response.set_cookie(
        key="dev_permission_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,  # 8 hours
    )

    logger.info(f"[DEV] Permission toggled: {permission} = {request_data.enabled}")

    return {
        "status": "updated",
        "permission": permission,
        "enabled": request_data.enabled,
        "current_overrides": overrides,
    }


@router.post("/permissions/add")
async def add_permissions(
    request_data: AddPermissionsRequest,
    request: Request,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Add multiple permissions temporarily.

    Useful for testing features that require multiple permissions.
    """
    overrides = get_permission_overrides(request)

    for perm in request_data.permissions:
        if perm not in overrides.get("added", []):
            overrides.setdefault("added", []).append(perm)
        # Remove from 'removed' if present
        if perm in overrides.get("removed", []):
            overrides["removed"].remove(perm)

    response.set_cookie(
        key="dev_permission_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )

    logger.info(f"[DEV] Permissions added: {request_data.permissions}")

    return {
        "status": "added",
        "permissions_added": request_data.permissions,
        "current_overrides": overrides,
    }


@router.post("/permissions/remove")
async def remove_permissions(
    request_data: RemovePermissionsRequest,
    request: Request,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Remove multiple permissions temporarily.

    Useful for testing what happens when specific permissions are missing.
    """
    overrides = get_permission_overrides(request)

    for perm in request_data.permissions:
        if perm not in overrides.get("removed", []):
            overrides.setdefault("removed", []).append(perm)
        # Remove from 'added' if present
        if perm in overrides.get("added", []):
            overrides["added"].remove(perm)

    response.set_cookie(
        key="dev_permission_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )

    logger.info(f"[DEV] Permissions removed: {request_data.permissions}")

    return {
        "status": "removed",
        "permissions_removed": request_data.permissions,
        "current_overrides": overrides,
    }


@router.get("/permissions/overrides", response_model=PermissionOverrides)
async def get_current_overrides(
    request: Request,
    _: bool = Depends(dev_only),
) -> PermissionOverrides:
    """Get the current permission overrides."""
    overrides = get_permission_overrides(request)
    return PermissionOverrides(
        added=overrides.get("added", []),
        removed=overrides.get("removed", []),
    )


@router.post("/permissions/reset")
async def reset_permission_overrides(
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """Reset all permission overrides to defaults (use profile permissions only)."""
    response.delete_cookie("dev_permission_overrides")

    logger.info("[DEV] Permission overrides reset")

    return {
        "status": "reset",
        "message": "All permission overrides cleared. Using profile permissions only.",
    }


@router.post("/permissions/set-exact")
async def set_exact_permissions(
    permissions: list[str],
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Set exact permissions, ignoring the profile.

    This completely overrides the profile permissions with the provided list.
    Useful for testing very specific permission combinations.

    Usage:
        POST /api/dev/permissions/set-exact
        Body: ["sales:proposals:read", "sales:proposals:create"]
    """
    # Store as "exact" mode - frontend/middleware should handle this specially
    overrides = {
        "mode": "exact",
        "exact_permissions": permissions,
        "added": [],
        "removed": [],
    }

    response.set_cookie(
        key="dev_permission_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )

    logger.info(f"[DEV] Exact permissions set: {permissions}")

    return {
        "status": "set",
        "mode": "exact",
        "permissions": permissions,
    }


# =============================================================================
# COMPANY ACCESS TOGGLE ENDPOINTS
# =============================================================================

@router.post("/companies/toggle")
async def toggle_company(
    request_data: ToggleCompanyRequest,
    request: Request,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Toggle a single company on/off for testing.

    - If `enabled=true`: Adds the company to the user's accessible companies
    - If `enabled=false`: Removes the company from the user's accessible companies

    This allows testing company access scenarios without changing the persona.
    """
    overrides = get_company_overrides(request)
    company = request_data.company

    if request_data.enabled:
        # Add company
        if company not in overrides.get("added", []):
            overrides.setdefault("added", []).append(company)
        # Remove from 'removed' if present
        if company in overrides.get("removed", []):
            overrides["removed"].remove(company)
    else:
        # Remove company
        if company not in overrides.get("removed", []):
            overrides.setdefault("removed", []).append(company)
        # Remove from 'added' if present
        if company in overrides.get("added", []):
            overrides["added"].remove(company)

    # Save to cookie
    response.set_cookie(
        key="dev_company_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,  # 8 hours
    )

    logger.info(f"[DEV] Company toggled: {company} = {request_data.enabled}")

    return {
        "status": "updated",
        "company": company,
        "enabled": request_data.enabled,
        "current_overrides": overrides,
    }


@router.post("/companies/add")
async def add_companies(
    request_data: AddCompaniesRequest,
    request: Request,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Add multiple companies temporarily.

    Useful for testing features that require access to multiple companies.
    """
    overrides = get_company_overrides(request)

    for company in request_data.companies:
        if company not in overrides.get("added", []):
            overrides.setdefault("added", []).append(company)
        # Remove from 'removed' if present
        if company in overrides.get("removed", []):
            overrides["removed"].remove(company)

    response.set_cookie(
        key="dev_company_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )

    logger.info(f"[DEV] Companies added: {request_data.companies}")

    return {
        "status": "added",
        "companies_added": request_data.companies,
        "current_overrides": overrides,
    }


@router.post("/companies/remove")
async def remove_companies(
    request_data: RemoveCompaniesRequest,
    request: Request,
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Remove multiple companies temporarily.

    Useful for testing what happens when a user loses access to companies.
    """
    overrides = get_company_overrides(request)

    for company in request_data.companies:
        if company not in overrides.get("removed", []):
            overrides.setdefault("removed", []).append(company)
        # Remove from 'added' if present
        if company in overrides.get("added", []):
            overrides["added"].remove(company)

    response.set_cookie(
        key="dev_company_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )

    logger.info(f"[DEV] Companies removed: {request_data.companies}")

    return {
        "status": "removed",
        "companies_removed": request_data.companies,
        "current_overrides": overrides,
    }


@router.get("/companies/overrides", response_model=CompanyOverrides)
async def get_current_company_overrides(
    request: Request,
    _: bool = Depends(dev_only),
) -> CompanyOverrides:
    """Get the current company overrides."""
    overrides = get_company_overrides(request)
    return CompanyOverrides(
        added=overrides.get("added", []),
        removed=overrides.get("removed", []),
    )


@router.post("/companies/reset")
async def reset_company_overrides(
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """Reset all company overrides to defaults (use profile companies only)."""
    response.delete_cookie("dev_company_overrides")

    logger.info("[DEV] Company overrides reset")

    return {
        "status": "reset",
        "message": "All company overrides cleared. Using profile companies only.",
    }


@router.post("/companies/set-exact")
async def set_exact_companies(
    companies: list[str],
    response: Response,
    _: bool = Depends(dev_only),
) -> dict:
    """
    Set exact companies, ignoring the profile.

    This completely overrides the profile companies with the provided list.
    Useful for testing very specific company access scenarios.

    Usage:
        POST /api/dev/companies/set-exact
        Body: ["backlite_dubai", "viola_communications"]
    """
    overrides = {
        "mode": "exact",
        "exact_companies": companies,
        "added": [],
        "removed": [],
    }

    response.set_cookie(
        key="dev_company_overrides",
        value=json.dumps(overrides),
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )

    logger.info(f"[DEV] Exact companies set: {companies}")

    return {
        "status": "set",
        "mode": "exact",
        "companies": companies,
    }


@router.get("/companies")
async def list_all_companies(_: bool = Depends(dev_only)) -> list[str]:
    """List all available companies in the system from Asset Management."""
    settings = get_settings()

    if not settings.ASSET_MANAGEMENT_URL:
        logger.warning("[DEV] Asset Management URL not configured, returning empty list")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.ASSET_MANAGEMENT_URL}/api/companies")
            response.raise_for_status()
            data = response.json()
            # Return just the company codes (leaf companies)
            return data.get("companies", [])
    except httpx.TimeoutException:
        logger.error("[DEV] Timeout fetching companies from Asset Management")
        return []
    except httpx.ConnectError as e:
        logger.error(f"[DEV] Connection error fetching companies: {e}")
        return []
    except Exception as e:
        logger.error(f"[DEV] Error fetching companies: {e}")
        return []
