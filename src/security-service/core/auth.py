"""
Authentication Service.

Handles JWT token validation and user authentication.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

import jwt

from config import settings
from db import db
from models import AuthUser, UserContext

logger = logging.getLogger("security-service")


class AuthService:
    """
    Authentication service for token validation and user context building.

    Validates JWT tokens against UI Supabase and builds RBAC context.
    """

    def __init__(self):
        self._jwt_secret = settings.SERVICE_API_SECRET
        self._jwt_algorithm = "HS256"

    # =========================================================================
    # TOKEN VALIDATION
    # =========================================================================

    def validate_token(self, token: str) -> dict[str, Any]:
        """
        Validate a JWT token and return user info with RBAC context.

        Args:
            token: JWT token string

        Returns:
            {
                "valid": bool,
                "user": AuthUser dict if valid,
                "rbac_context": Full RBAC context if valid,
                "expires_at": Expiration time if valid,
                "error": Error message if invalid
            }
        """
        try:
            # Decode JWT
            payload = self._decode_token(token)
            if not payload:
                return {"valid": False, "error": "Invalid token"}

            user_id = payload.get("sub") or payload.get("user_id")
            if not user_id:
                return {"valid": False, "error": "No user ID in token"}

            # Get user from UI Supabase
            user = db.get_user(user_id)
            if not user:
                return {"valid": False, "error": "User not found"}

            # Build RBAC context
            rbac_context = db.get_full_user_context(user_id)
            if not rbac_context:
                return {"valid": False, "error": "Failed to build RBAC context"}

            return {
                "valid": True,
                "user": {
                    "id": user_id,
                    "email": user.get("email", ""),
                    "name": user.get("name"),
                    "profile": rbac_context.get("profile"),
                },
                "rbac_context": rbac_context,
                "expires_at": payload.get("exp"),
            }

        except jwt.ExpiredSignatureError:
            return {"valid": False, "error": "Token expired"}
        except jwt.InvalidTokenError as e:
            logger.warning(f"[AUTH] Invalid token: {e}")
            return {"valid": False, "error": "Invalid token"}
        except Exception as e:
            logger.error(f"[AUTH] Token validation error: {e}")
            return {"valid": False, "error": "Validation error"}

    def _decode_token(self, token: str) -> dict | None:
        """
        Decode JWT token.

        Tries multiple secrets if configured.
        """
        if not self._jwt_secret:
            logger.warning("[AUTH] JWT secret not configured")
            return None

        try:
            return jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
                options={"verify_exp": True},
            )
        except Exception:
            return None

    # =========================================================================
    # SERVICE TOKENS
    # =========================================================================

    def generate_service_token(self, service_name: str) -> dict[str, Any]:
        """
        Generate a short-lived JWT for service-to-service communication.

        Args:
            service_name: Name of the calling service

        Returns:
            {
                "token": JWT token string,
                "expires_at": Expiration timestamp
            }
        """
        if not self._jwt_secret:
            raise ValueError("JWT secret not configured")

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=settings.SERVICE_TOKEN_EXPIRY_SECONDS)

        payload = {
            "service": service_name,
            "type": "service",
            "iat": now,
            "exp": expires_at,
        }

        token = jwt.encode(payload, self._jwt_secret, algorithm=self._jwt_algorithm)

        return {
            "token": token,
            "expires_at": expires_at.isoformat(),
        }

    def validate_service_token(self, token: str) -> dict[str, Any]:
        """
        Validate a service-to-service token.

        Args:
            token: JWT token string

        Returns:
            {
                "valid": bool,
                "service": Service name if valid,
                "error": Error message if invalid
            }
        """
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
            )

            if payload.get("type") != "service":
                return {"valid": False, "error": "Not a service token"}

            service_name = payload.get("service")
            if not service_name:
                return {"valid": False, "error": "No service name in token"}

            return {
                "valid": True,
                "service": service_name,
            }

        except jwt.ExpiredSignatureError:
            return {"valid": False, "error": "Token expired"}
        except jwt.InvalidTokenError as e:
            logger.warning(f"[AUTH] Invalid service token: {e}")
            return {"valid": False, "error": "Invalid token"}

    # =========================================================================
    # USER CONTEXT
    # =========================================================================

    def get_user_context(self, user_id: str) -> UserContext | None:
        """
        Get full RBAC context for a user.

        Args:
            user_id: User ID

        Returns:
            UserContext with full 5-level RBAC data
        """
        context = db.get_full_user_context(user_id)
        if not context:
            return None

        return UserContext(
            id=context.get("user_id", user_id),
            email=context.get("email", ""),
            name=context.get("name"),
            profile=context.get("profile"),
            permissions=context.get("permissions", []),
            permission_sets=context.get("permission_sets", []),
            teams=context.get("teams", []),
            team_ids=context.get("team_ids", []),
            manager_id=context.get("manager_id"),
            subordinate_ids=context.get("subordinate_ids", []),
            sharing_rules=context.get("sharing_rules", []),
            shared_records=context.get("shared_records", {}),
            shared_from_user_ids=context.get("shared_from_user_ids", []),
            companies=context.get("companies", []),
        )


# Singleton instance
auth_service = AuthService()
