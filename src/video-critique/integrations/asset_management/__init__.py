"""
Asset Management Integration.

Client for communicating with the asset-management service to link
filmed video locations to the asset library.
"""

from integrations.asset_management.client import AssetManagementClient, get_asset_client

__all__ = ["AssetManagementClient", "get_asset_client"]
