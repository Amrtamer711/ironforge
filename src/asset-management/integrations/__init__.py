"""
Integrations for Asset Management Service.

Provides clients for inter-service communication.
"""

from integrations.sales_module import SalesModuleClient, get_sales_module_client

__all__ = [
    "SalesModuleClient",
    "get_sales_module_client",
]
