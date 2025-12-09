"""
Sales module - permissions for the sales proposal system.

This module provides RBAC permissions for:
- Proposals
- Booking Orders
- Mockups
- Templates
"""

from typing import List

from integrations.rbac.base import Permission
from integrations.rbac.modules.registry import ModuleDefinition


class SalesModule(ModuleDefinition):
    """
    Sales proposal module.

    Permission format: sales:{resource}:{action}
    """

    @property
    def name(self) -> str:
        return "sales"

    @property
    def display_name(self) -> str:
        return "Sales Proposals"

    @property
    def description(self) -> str:
        return "Sales proposal generation, booking orders, and mockup management"

    def get_permissions(self) -> List[Permission]:
        return [
            # Proposals
            Permission.from_name("sales:proposals:create", "Create new proposals"),
            Permission.from_name("sales:proposals:read", "View proposals"),
            Permission.from_name("sales:proposals:update", "Edit proposals"),
            Permission.from_name("sales:proposals:delete", "Delete proposals"),
            Permission.from_name("sales:proposals:manage", "Full control over proposals"),

            # Booking Orders
            Permission.from_name("sales:booking_orders:create", "Create booking orders"),
            Permission.from_name("sales:booking_orders:read", "View booking orders"),
            Permission.from_name("sales:booking_orders:update", "Edit booking orders"),
            Permission.from_name("sales:booking_orders:delete", "Delete booking orders"),
            Permission.from_name("sales:booking_orders:manage", "Full control over booking orders"),

            # Mockups
            Permission.from_name("sales:mockups:create", "Create mockups"),
            Permission.from_name("sales:mockups:read", "View mockups"),
            Permission.from_name("sales:mockups:update", "Edit mockups"),
            Permission.from_name("sales:mockups:delete", "Delete mockups"),
            Permission.from_name("sales:mockups:manage", "Full control over mockups"),

            # Templates
            Permission.from_name("sales:templates:read", "View templates"),
            Permission.from_name("sales:templates:create", "Create templates"),
            Permission.from_name("sales:templates:update", "Edit templates"),
            Permission.from_name("sales:templates:delete", "Delete templates"),
            Permission.from_name("sales:templates:manage", "Full control over templates"),

            # Clients
            Permission.from_name("sales:clients:read", "View clients"),
            Permission.from_name("sales:clients:create", "Create clients"),
            Permission.from_name("sales:clients:update", "Edit clients"),
            Permission.from_name("sales:clients:delete", "Delete clients"),
            Permission.from_name("sales:clients:manage", "Full control over clients"),

            # Products
            Permission.from_name("sales:products:read", "View products"),
            Permission.from_name("sales:products:create", "Create products"),
            Permission.from_name("sales:products:update", "Edit products"),
            Permission.from_name("sales:products:delete", "Delete products"),
            Permission.from_name("sales:products:manage", "Full control over products"),

            # Reports
            Permission.from_name("sales:reports:read", "View reports"),
            Permission.from_name("sales:reports:export", "Export reports"),
        ]
