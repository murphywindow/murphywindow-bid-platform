"""Typed transport contracts for multi-field estimating commands."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class MasterRecordCommand(BaseModel):
    """Entity-specific reusable record fields accepted by Add New/update."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    expected_revision: int | None = None
    display_name: str | None = None
    name: str | None = None
    legal_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    classifications: list[str] = Field(default_factory=list)
    address: str | None = None
    website: str | None = None
    primary_phone: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    organization_id: str | None = None
    organization: str | None = None
    position: str | None = None
    role: str | None = None
    roles: list[str] = Field(default_factory=list)
    office_phone: str | None = None
    mobile_phone: str | None = None
    update_scope: Literal["master"] = "master"


class CustomCostCodeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr
    code: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    mwd_code: str = Field(default="", max_length=100)
    mwd_description: str = Field(default="", max_length=1000)
    deduct: bool = False
    reason: str = Field(default="Authorized custom Cost Code exception", max_length=1000)


class RemoveCostCodeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    confirm_cascade: bool = False
    reason: str = Field(default="Remove project Cost Code", max_length=1000)


class BidSourceEditCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    source_type: Literal["quote", "frame", "door", "equipment", "labor", "borrowed_lite"]
    source_id: str = Field(min_length=1, max_length=200)
    changes: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool
    reason: str = Field(default="Bid detail canonical-source edit", max_length=1000)
    correlation_id: str | None = Field(default=None, max_length=200)


class PasteCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: Literal[
        "cost_codes", "quotes", "doors", "equipment", "borrowed_lites",
        "labor_estimates", "contacts",
    ]
    row_id: str | None = None
    field: str = Field(min_length=1, max_length=100)
    value: Any = None


class PasteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    cells: list[PasteCell] = Field(min_length=1, max_length=10_000)
    correlation_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="Clipboard paste", max_length=1000)
