"""Simple scope / permission checks for cloud mode."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Permission:
    """A single permission string, e.g. ``search:read``."""

    name: str

    def __str__(self) -> str:
        return self.name


# Well-known permissions
PERM_SEARCH_READ = Permission("search:read")
PERM_SEARCH_WRITE = Permission("search:write")
PERM_FETCH_READ = Permission("fetch:read")
PERM_DEEP_READ = Permission("deep:read")
PERM_DOCTOR_READ = Permission("doctor:read")
PERM_ADMIN = Permission("admin")
PERM_TOKEN_MANAGE = Permission("token:manage")


@dataclass
class ScopeSet:
    """Set of permission strings derived from a token's scopes field."""

    permissions: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, d: dict | None) -> ScopeSet:
        """Build from the JSON scopes dict stored on ApiToken.

        Expected shape: ``{"permissions": ["search:read", "fetch:read"]}``.
        ``None`` means no cloud permissions; admin must be explicit.
        """
        if d is None:
            return cls(permissions=frozenset())
        perms = d.get("permissions", [])
        if isinstance(perms, list):
            return cls(permissions=frozenset(str(p) for p in perms))
        return cls(permissions=frozenset())

    def allows(self, permission: str | Permission) -> bool:
        """Check if the scope set permits *permission*.

        An empty permissions set denies cloud access by default.
        """
        perm = str(permission)
        if not self.permissions:
            return False
        # admin grants everything
        if "admin" in self.permissions:
            return True
        return perm in self.permissions
