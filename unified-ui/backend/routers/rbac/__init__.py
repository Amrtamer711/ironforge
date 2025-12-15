"""
RBAC router package for unified-ui.

[VERIFIED] Mirrors server.js lines 2063-3950:
- Level 1: profiles.py - User/Profile endpoints (9 endpoints)
- Level 2: permission_sets.py - Permission Set endpoints (7 endpoints)
- Level 3: teams.py - Team Management endpoints (9 endpoints)
- Level 4: sharing.py - Record Sharing endpoints (12 endpoints)
- users.py - User management endpoints (6 endpoints)

43 endpoints total across 5 modules.
"""

from fastapi import APIRouter

from backend.routers.rbac.profiles import router as profiles_router
from backend.routers.rbac.permission_sets import router as permission_sets_router
from backend.routers.rbac.teams import router as teams_router
from backend.routers.rbac.sharing import router as sharing_router
from backend.routers.rbac.users import router as users_router

# Main RBAC router that combines all sub-routers
router = APIRouter(prefix="/api/rbac", tags=["rbac"])

# Include all sub-routers
router.include_router(profiles_router)
router.include_router(permission_sets_router)
router.include_router(teams_router)
router.include_router(sharing_router)
router.include_router(users_router)
