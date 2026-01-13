"""
RBAC router package for unified-ui.

Complete RBAC system for admin panel:
- profiles.py - Profile management + permissions CRUD (11 endpoints)
- permission_sets.py - Permission Set management (8 endpoints)
- teams.py - Team Management (10 endpoints)
- sharing.py - Record Sharing (12 endpoints)
- users.py - User management (12 endpoints)
- companies.py - Company management via asset-management proxy (3 endpoints)

56 endpoints total across 6 modules.
"""

from fastapi import APIRouter

from backend.routers.rbac.companies import router as companies_router
from backend.routers.rbac.permission_sets import router as permission_sets_router
from backend.routers.rbac.profiles import router as profiles_router
from backend.routers.rbac.sharing import router as sharing_router
from backend.routers.rbac.teams import router as teams_router
from backend.routers.rbac.users import router as users_router

# Main RBAC router that combines all sub-routers
router = APIRouter(prefix="/api/rbac", tags=["rbac"])

# Include all sub-routers
router.include_router(profiles_router)
router.include_router(permission_sets_router)
router.include_router(teams_router)
router.include_router(sharing_router)
router.include_router(users_router)
router.include_router(companies_router)
