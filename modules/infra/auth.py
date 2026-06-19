"""Authentication strategies for Databricks workspace access."""

from __future__ import annotations

from dataclasses import dataclass

from modules.core.config import AppSettings


@dataclass(frozen=True, slots=True)
class AuthContext:
    mode: str
    principal: str
    has_workspace_access: bool


class AuthProvider:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def resolve(self) -> AuthContext:
        if self.settings.auth_mode == "service_principal":
            principal = self.settings.service_principal_client_id or "unknown-sp"
            has_access = bool(
                self.settings.service_principal_client_id
                and self.settings.service_principal_client_secret
            )
            return AuthContext(
                mode="service_principal",
                principal=principal,
                has_workspace_access=has_access,
            )
        principal = "workspace-user"
        has_access = bool(self.settings.databricks_token)
        return AuthContext(
            mode="user_workspace",
            principal=principal,
            has_workspace_access=has_access,
        )
