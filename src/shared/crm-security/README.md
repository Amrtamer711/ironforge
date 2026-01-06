# CRM Security SDK

Security SDK for MMG Service Platform providing RBAC, audit logging, and trusted header parsing.

## Installation

```bash
# From git (recommended)
pip install "crm-security @ git+https://github.com/org/CRM.git#subdirectory=src/security/sdk"

# With FastAPI support
pip install "crm-security[fastapi] @ git+https://github.com/org/CRM.git#subdirectory=src/security/sdk"

# Local development
pip install -e src/security/sdk[fastapi]
```

## Usage

### FastAPI Authentication

```python
from fastapi import Depends
from crm_security import require_auth, require_permission, UserContext

@router.get("/protected")
async def protected_endpoint(user: UserContext = Depends(require_auth)):
    return {"user_id": user.id}

@router.post("/locations")
async def create_location(
    user: UserContext = Depends(require_permission("assets:locations:create"))
):
    return {"created_by": user.id}
```

### Audit Logging

```python
from crm_security import audit_log

# Log an event (async HTTP to security-service)
await audit_log(
    actor_type="user",
    actor_id=user.id,
    action="create",
    resource_type="proposal",
    resource_id="PROP-001",
)

# Or use decorator
from crm_security import audit

@audit(action="create", resource_type="proposal")
async def create_proposal(user: UserContext, data: ProposalCreate):
    ...
```

### RBAC Checks

```python
from crm_security import has_permission, has_any_permission

# Check permissions locally (no network)
if has_permission(user.permissions, "sales:proposals:create"):
    ...

if has_any_permission(user.permissions, ["sales:proposals:read", "sales:proposals:manage"]):
    ...
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SECURITY_SERVICE_URL` | URL of security-service (default: `http://localhost:8002`) |
| `SERVICE_API_SECRET` | Secret for service-to-service auth |
| `PROXY_SECRET` | Secret for trusted proxy verification |

## Architecture

```
Browser → unified-ui (validates JWT) → Backend Services
                ↓
        Injects X-Trusted-User-* headers
                ↓
        SDK parses headers locally (no network)
                ↓
        Audit logs sent async to security-service
```
