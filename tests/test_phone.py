import pytest
from pydantic import ValidationError

from app.api_models import MasterRecordCommand
from app.phone import normalize_phone_number
from app.project_commands import validate_project_inputs
from app.schema import default_configuration, new_project
from app.services import DomainError


def test_phone_is_stored_as_formatted_text_from_exactly_ten_digits():
    assert normalize_phone_number("1231231234") == "(123) 123-1234"
    assert normalize_phone_number("(123) 123-1234") == "(123) 123-1234"
    with pytest.raises(ValueError):
        normalize_phone_number(1231231234)
    with pytest.raises(ValueError):
        normalize_phone_number("123-1234")
    with pytest.raises(ValueError):
        normalize_phone_number("1-123-123-1234")


def test_master_data_phone_contract_normalizes_and_rejects_non_string_values():
    command = MasterRecordCommand(display_name="Example", primary_phone="6125550100")
    assert command.primary_phone == "(612) 555-0100"
    with pytest.raises(ValidationError):
        MasterRecordCommand(display_name="Example", primary_phone=6125550100)


def test_project_phone_validation_formats_changes_and_preserves_untouched_legacy_values():
    current = new_project("Phone test", "Estimator", "Estimator")
    incoming = {**current, "project": {**current["project"], "owner_phone": "6125550199"}}
    validate_project_inputs(incoming, current, default_configuration())
    assert incoming["project"]["owner_phone"] == "(612) 555-0199"

    invalid = {**current, "project": {**current["project"], "owner_phone": "555-0199"}}
    with pytest.raises(DomainError, match="ten-digit phone number"):
        validate_project_inputs(invalid, current, default_configuration())

    legacy = {**current, "project": {**current["project"], "owner_phone": "555-0199"}}
    unchanged = {**legacy, "project": dict(legacy["project"])}
    validate_project_inputs(unchanged, legacy, default_configuration())
    assert unchanged["project"]["owner_phone"] == "555-0199"
