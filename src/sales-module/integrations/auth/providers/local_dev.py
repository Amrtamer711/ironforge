"""
Local development authentication provider.

Implements AuthProvider using hardcoded users for local development.
No external auth service required.
"""

import hashlib
import logging
import uuid
from typing import Any

from integrations.auth.base import (
    AuthProvider,
    AuthResult,
    AuthStatus,
    AuthUser,
    TokenPayload,
)
from core.utils.time import get_uae_time

logger = logging.getLogger("proposal-bot")


# Default development users
DEFAULT_DEV_USERS = {
    "admin@mmg.com": {
        "id": "dev-admin-001",
        "name": "Admin User",
        "role": "admin",
    },
    "hos@mmg.com": {
        "id": "dev-hos-001",
        "name": "Head of Sales",
        "role": "hos",
    },
    "sales@mmg.com": {
        "id": "dev-sales-001",
        "name": "Sales Person",
        "role": "sales_person",
    },
    "coordinator@mmg.com": {
        "id": "dev-coord-001",
        "name": "Coordinator",
        "role": "coordinator",
    },
    "finance@mmg.com": {
        "id": "dev-finance-001",
        "name": "Finance User",
        "role": "finance",
    },
}


class LocalDevAuthProvider(AuthProvider):
    """
    Local development auth provider.

    Uses hardcoded users for testing without external auth.
    Tokens are simple email-based hashes for simulation.

    Usage:
        provider = LocalDevAuthProvider()

        # "Log in" by generating a token from email
        token = provider.generate_dev_token("admin@mmg.com")

        # Verify the token
        result = await provider.verify_token(token)
    """

    def __init__(self, custom_users: dict[str, dict] | None = None):
        """
        Initialize local dev provider.

        Args:
            custom_users: Optional custom user definitions to add/override defaults
        """
        self._users = dict(DEFAULT_DEV_USERS)
        if custom_users:
            self._users.update(custom_users)

        # In-memory user database (for create/update/delete)
        self._db_users: dict[str, AuthUser] = {}

        # Initialize default users in memory DB
        for email, data in self._users.items():
            self._db_users[data["id"]] = AuthUser(
                id=data["id"],
                email=email,
                name=data.get("name"),
                is_active=True,
                local_id=data["id"],
                metadata={"role": data.get("role", "sales_person")},
            )

        logger.info(f"[AUTH:LOCAL] Initialized with {len(self._users)} users")

    @property
    def name(self) -> str:
        return "local_dev"

    def generate_dev_token(self, email: str) -> str:
        """
        Generate a development token for an email.

        The token is a simple hash that encodes the email.
        This is NOT secure - only for development!

        Args:
            email: User email

        Returns:
            Development token string
        """
        # Simple token format: dev_<hash>_<email_base64>
        import base64
        email_b64 = base64.b64encode(email.encode()).decode()
        hash_part = hashlib.sha256(f"dev_secret_{email}".encode()).hexdigest()[:16]
        return f"dev_{hash_part}_{email_b64}"

    def _decode_dev_token(self, token: str) -> str | None:
        """Decode a dev token to extract email."""
        try:
            import base64

            if not token.startswith("dev_"):
                return None

            parts = token.split("_", 2)
            if len(parts) != 3:
                return None

            email = base64.b64decode(parts[2].encode()).decode()
            return email

        except Exception:
            return None

    async def verify_token(self, token: str) -> AuthResult:
        """Verify a dev token."""
        try:
            email = self._decode_dev_token(token)

            if not email:
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error="Invalid dev token format"
                )

            # Look up user
            user_data = self._users.get(email)
            if not user_data:
                return AuthResult(
                    success=False,
                    status=AuthStatus.INVALID,
                    error=f"Unknown user: {email}"
                )

            user = AuthUser(
                id=user_data["id"],
                email=email,
                name=user_data.get("name"),
                is_active=True,
                local_id=user_data["id"],
                metadata={"role": user_data.get("role", "sales_person")},
                access_token=token,
            )

            logger.debug(f"[AUTH:LOCAL] Verified token for: {email}")

            return AuthResult(
                success=True,
                user=user,
                status=AuthStatus.AUTHENTICATED,
                token=token,
            )

        except Exception as e:
            logger.error(f"[AUTH:LOCAL] Token verification failed: {e}")
            return AuthResult(
                success=False,
                status=AuthStatus.INVALID,
                error=str(e)
            )

    async def get_user_by_id(self, user_id: str) -> AuthUser | None:
        """Get user by ID from in-memory database."""
        return self._db_users.get(user_id)

    async def get_user_by_email(self, email: str) -> AuthUser | None:
        """Get user by email."""
        user_data = self._users.get(email)
        if user_data:
            return self._db_users.get(user_data["id"])
        return None

    async def sync_user_to_db(self, user: AuthUser) -> bool:
        """Sync user to application database."""
        try:
            from db.database import db

            # Check if backend supports user operations
            if not hasattr(db._backend, 'upsert_user'):
                logger.warning("[AUTH:LOCAL] Database backend doesn't support upsert_user")
                return False

            now = get_uae_time().isoformat()

            return db._backend.upsert_user(
                user_id=user.id,
                email=user.email,
                full_name=user.name,
                avatar_url=user.avatar_url,
                last_login=now,
            )

        except Exception as e:
            logger.error(f"[AUTH:LOCAL] Sync user to DB failed: {e}")
            return False

    async def create_user(
        self,
        email: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthUser | None:
        """Create a new user in memory."""
        try:
            if email in self._users:
                logger.warning(f"[AUTH:LOCAL] User already exists: {email}")
                return None

            user_id = f"dev-{uuid.uuid4().hex[:8]}"

            user = AuthUser(
                id=user_id,
                email=email,
                name=name,
                is_active=True,
                local_id=user_id,
                metadata=metadata or {},
            )

            self._users[email] = {
                "id": user_id,
                "name": name,
                "role": (metadata or {}).get("role", "sales_person"),
            }
            self._db_users[user_id] = user

            logger.info(f"[AUTH:LOCAL] Created user: {email}")
            return user

        except Exception as e:
            logger.error(f"[AUTH:LOCAL] Create user failed: {e}")
            return None

    async def update_user(
        self,
        user_id: str,
        name: str | None = None,
        avatar_url: str | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthUser | None:
        """Update user in memory."""
        try:
            user = self._db_users.get(user_id)
            if not user:
                return None

            if name is not None:
                user.name = name
            if avatar_url is not None:
                user.avatar_url = avatar_url
            if is_active is not None:
                user.is_active = is_active
            if metadata is not None:
                user.metadata.update(metadata)

            # Update _users dict too
            if user.email in self._users:
                self._users[user.email]["name"] = user.name
                if metadata and "role" in metadata:
                    self._users[user.email]["role"] = metadata["role"]

            return user

        except Exception as e:
            logger.error(f"[AUTH:LOCAL] Update user failed: {e}")
            return None

    async def delete_user(self, user_id: str) -> bool:
        """Delete user from memory."""
        try:
            user = self._db_users.get(user_id)
            if not user:
                return False

            del self._db_users[user_id]
            if user.email in self._users:
                del self._users[user.email]

            logger.info(f"[AUTH:LOCAL] Deleted user: {user_id}")
            return True

        except Exception as e:
            logger.error(f"[AUTH:LOCAL] Delete user failed: {e}")
            return False

    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        is_active: bool | None = None,
    ) -> list[AuthUser]:
        """List users from memory."""
        users = list(self._db_users.values())

        if is_active is not None:
            users = [u for u in users if u.is_active == is_active]

        return users[offset:offset + limit]

    def decode_token(self, token: str) -> TokenPayload | None:
        """Decode dev token."""
        email = self._decode_dev_token(token)
        if not email:
            return None

        user_data = self._users.get(email)
        if not user_data:
            return None

        return TokenPayload(
            sub=user_data["id"],
            email=email,
            role=user_data.get("role"),
            metadata={"role": user_data.get("role")},
        )

    def get_available_users(self) -> dict[str, dict]:
        """Get all available dev users (for UI display)."""
        return dict(self._users)
