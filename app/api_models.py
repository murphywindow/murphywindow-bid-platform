"""Typed transport contracts for multi-field estimating commands."""
from __future__ import annotations

from typing import Any, Literal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .phone import normalize_phone_number


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

    @field_validator("primary_phone", "phone", "office_phone", "mobile_phone", mode="before")
    @classmethod
    def normalize_phone_fields(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_phone_number(value)


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
    alternate_id: str | None = Field(default=None, max_length=200)


class AddSectionMaterialCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    name: str = Field(min_length=1, max_length=300)
    source: Literal["square_feet", "perimeter_lf", "head_sill_qty", "caulking_lf", "quantity", "tie_back_qty", "backpan_lf", "manual_quantity"]
    manual_quantity: float | None = None
    factor: float = 1
    operator: Literal["multiply", "divide", "add", "subtract"] = "multiply"
    operand: float | None = None
    unit: str = Field(default="each", min_length=1, max_length=50)
    controlled_rate_id: str | None = Field(default=None, max_length=200)
    project_rate: float | None = None
    cost_code: str | None = Field(default=None, max_length=100)
    actual_cost_code: str | None = Field(default=None, max_length=100)
    material_code: str = Field(default="PROJECT", max_length=100)
    notes: str = Field(default="", max_length=2000)
    apply_to_existing: bool = True


class RemoveSectionMaterialCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    confirm_dependencies: bool = False
    reason: str = Field(default="Remove project-specific Installation Material", max_length=1000)


class AlternateNameCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    name: str = Field(default="", max_length=300)
    reason: str = Field(default="Alternate name changed", max_length=1000)


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


class ProposalStatus(StrEnum):
    GENERATED = "generated"
    VOIDED = "voided"
    SUPERSEDED = "superseded"


class ProposalFingerprint(BaseModel):
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=r"^[a-f0-9]{64}$")
    canonical_schema_version: str = "1.0.0"


class ProposalAncestry(BaseModel):
    parent_proposal_id: str | None = None
    ancestor_ids: list[str] = Field(default_factory=list)
    ancestry_status: Literal["known", "root_or_unknown", "legacy_unknown"] = "root_or_unknown"


class ProposalArtifactReference(BaseModel):
    id: str
    proposal_id: str
    snapshot_fingerprint: str
    template_version: str
    sha256: str
    immutable: Literal[True] = True


class ProposalVoidMetadata(BaseModel):
    reason: str = Field(min_length=1)
    voided_at: str
    voided_by: str
    voided_by_role: str


class ProposalMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    sequence: int = Field(ge=1)
    number: str = Field(pattern=r"^P[1-9][0-9]*$")
    name: str = Field(min_length=1)
    generated_at: str
    generated_by: str
    parent_proposal_id: str | None = None
    ancestor_ids: list[str] = Field(default_factory=list)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_id: str
    status: ProposalStatus
    void: ProposalVoidMetadata | None = None
    summary: dict[str, Any]
    snapshot_schema_version: str


class ProposalSnapshot(BaseModel):
    schema_version: str
    metadata: ProposalMetadata
    state: dict[str, Any]
    artifact: dict[str, Any]


class WorkingBranchSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    source_proposal_id: str
    source_proposal_number: str
    source_proposal_name: str
    created_at: str
    created_by: str
    correlation_id: str | None = None
    first_edit: dict[str, Any] | None = None
    inherited_configuration_id: str
    configuration_refresh_status: Literal["not_refreshed"] = "not_refreshed"


class ProposalComparison(BaseModel):
    left: ProposalMetadata
    right: ProposalMetadata
    header: str
    identical: bool
    summary: dict[str, Any]
    cost_codes: list[dict[str, Any]]
    alternates: dict[str, Any]
    proposal_language: dict[str, Any]
