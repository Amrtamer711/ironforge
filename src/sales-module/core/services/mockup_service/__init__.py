"""
Mockup Service - Core mockup generation orchestration.

Provides:
- PackageExpander: Expands packages to constituent networks with storage info
- ResponseBuilder: Builds frontend-friendly grouped responses

The mockup service handles the complexity of:
- Package → Network expansion
- Standalone vs Traditional network detection
- Storage key resolution (network-level vs asset-level)
- Result aggregation and grouping

Usage:
    from core.services.mockup_service import PackageExpander

    expander = PackageExpander(user_companies=["backlite_dubai"])
    targets = await expander.expand("dubai_bundle")  # Package or network key

    # targets is a list of generation targets:
    # [
    #     {
    #         "network_key": "dubai_gateway",
    #         "network_name": "Dubai Gateway",
    #         "is_standalone": True,
    #         "storage_keys": ["dubai_gateway"],
    #         "company": "backlite_dubai"
    #     },
    #     {
    #         "network_key": "mall_of_emirates",
    #         "network_name": "Mall of Emirates",
    #         "is_standalone": False,
    #         "storage_keys": ["moe_north", "moe_south", "moe_east"],
    #         "company": "backlite_dubai"
    #     }
    # ]
"""

from .package_expander import PackageExpander, GenerationTarget
from .response_builder import MockupResponseBuilder, MockupResult, NetworkResult

__all__ = [
    "PackageExpander",
    "GenerationTarget",
    "MockupResponseBuilder",
    "MockupResult",
    "NetworkResult",
]
