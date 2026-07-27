"""Application boundary for persistent settings and master-data management."""

from __future__ import annotations

from outsource_mail_collector.infrastructure.db.repository import (
    Employee,
    SQLiteRepository,
    Vendor,
)
from outsource_mail_collector.infrastructure.outlook_adapter import OutlookAdapter


class SettingsService:
    def __init__(
        self, repository: SQLiteRepository, outlook_adapter: OutlookAdapter
    ) -> None:
        self._repository = repository
        self._outlook = outlook_adapter

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        value = self._repository.get_setting(key)
        return default if value is None else value

    def set_setting(self, key: str, value: str) -> None:
        self._repository.set_setting(key, value)

    def list_employees(self, active_only: bool = False) -> list[Employee]:
        return self._repository.list_employees(active_only)

    def save_employee(
        self,
        employee_id: int | None,
        name: str,
        email: str,
        aliases: list[str],
        active: bool,
    ) -> Employee:
        return self._repository.save_employee(
            employee_id, name, email, aliases, active
        )

    def delete_employee(self, employee_id: int) -> None:
        self._repository.delete_employee(employee_id)

    def list_vendors(self, active_only: bool = False) -> list[Vendor]:
        return self._repository.list_vendors(active_only)

    def save_vendor(
        self,
        vendor_id: int | None,
        canonical_name: str,
        aliases: list[str],
        active: bool,
    ) -> Vendor:
        return self._repository.save_vendor(
            vendor_id, canonical_name, aliases, active
        )

    def delete_vendor(self, vendor_id: int) -> None:
        self._repository.delete_vendor(vendor_id)

    def list_outlook_folders(self) -> list[str]:
        self._outlook.connect()
        return self._outlook.list_folders()
