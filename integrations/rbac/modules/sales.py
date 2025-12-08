"""
Sales module - permissions and roles for the sales proposal system.

This module provides RBAC configuration for:
- Proposals
- Booking Orders
- Mockups
- Sales-specific roles (HOS, Sales Person, Coordinator, Finance)
"""

from typing import List, Optional

from integrations.rbac.base import Permission, Role
from integrations.rbac.modules.registry import ModuleDefinition


class SalesModule(ModuleDefinition):
    """
    Sales proposal module.

    Permission format: sales:{resource}:{action}
    Role format: sales:{role_name}
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
        ]

    def get_roles(self) -> List[Role]:
        return [
            Role(
                name="sales:admin",
                description="Full sales module access",
                permissions=[
                    Permission.from_name("sales:proposals:manage"),
                    Permission.from_name("sales:booking_orders:manage"),
                    Permission.from_name("sales:mockups:manage"),
                    Permission.from_name("sales:templates:manage"),
                ],
                is_system=True,
            ),
            Role(
                name="sales:hos",
                description="Head of Sales - Team oversight",
                permissions=[
                    Permission.from_name("sales:proposals:manage"),
                    Permission.from_name("sales:booking_orders:manage"),
                    Permission.from_name("sales:mockups:manage"),
                    Permission.from_name("sales:templates:read"),
                    Permission.from_name("core:users:read"),
                    Permission.from_name("core:ai_costs:read"),
                ],
                is_system=True,
            ),
            Role(
                name="sales:sales_person",
                description="Sales team member",
                permissions=[
                    Permission.from_name("sales:proposals:create"),
                    Permission.from_name("sales:proposals:read"),
                    Permission.from_name("sales:booking_orders:create"),
                    Permission.from_name("sales:booking_orders:read"),
                    Permission.from_name("sales:mockups:create"),
                    Permission.from_name("sales:mockups:read"),
                    Permission.from_name("sales:templates:read"),
                ],
                is_system=True,
            ),
            Role(
                name="sales:coordinator",
                description="Operations coordinator",
                permissions=[
                    Permission.from_name("sales:booking_orders:create"),
                    Permission.from_name("sales:booking_orders:read"),
                    Permission.from_name("sales:booking_orders:update"),
                ],
                is_system=True,
            ),
            Role(
                name="sales:finance",
                description="Finance team member",
                permissions=[
                    Permission.from_name("sales:booking_orders:read"),
                    Permission.from_name("core:ai_costs:read"),
                ],
                is_system=True,
            ),
        ]

    def get_default_role(self) -> Optional[str]:
        return "sales:sales_person"
