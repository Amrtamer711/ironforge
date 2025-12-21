"""Core modules - schemas and business logic combined."""

from core.asset_types import (
    AssetType,
    AssetTypeCreate,
    AssetTypeService,
    AssetTypeUpdate,
)
from core.eligibility import (
    SERVICE_REQUIREMENTS,
    BulkEligibilityItem,
    EligibilityCheck,
    EligibilityReason,
    EligibilityService,
    ServiceEligibility,
)
from core.locations import (
    Location,
    LocationCreate,
    LocationService,
    LocationUpdate,
)
from core.networks import (
    Network,
    NetworkCreate,
    NetworkService,
    NetworkUpdate,
)
from core.packages import (
    Package,
    PackageCreate,
    PackageItem,
    PackageService,
    PackageUpdate,
)

__all__ = [
    # Networks
    "Network",
    "NetworkCreate",
    "NetworkUpdate",
    "NetworkService",
    # Asset Types
    "AssetType",
    "AssetTypeCreate",
    "AssetTypeUpdate",
    "AssetTypeService",
    # Locations
    "Location",
    "LocationCreate",
    "LocationUpdate",
    "LocationService",
    # Packages
    "Package",
    "PackageItem",
    "PackageCreate",
    "PackageUpdate",
    "PackageService",
    # Eligibility
    "ServiceEligibility",
    "EligibilityReason",
    "EligibilityCheck",
    "BulkEligibilityItem",
    "EligibilityService",
    "SERVICE_REQUIREMENTS",
]
