"""
HTTP clients for inter-service communication.

All clients use JWT-based service-to-service authentication
via the crm_security.ServiceAuthClient.
"""

from .asset_management import AssetManagementClient, asset_mgmt_client

__all__ = [
    "AssetManagementClient",
    "asset_mgmt_client",
]
