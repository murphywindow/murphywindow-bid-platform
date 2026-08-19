from decimal import Decimal

import pytest

from app.mileage import MileageError, calculate_driving_mileage


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.responses.pop(0))


def test_driving_mileage_uses_census_then_osrm_and_rounds_to_one_decimal():
    meters = Decimal("12.36") * Decimal("1609.344")
    client = FakeClient([
        {"result": {"addressMatches": [{"matchedAddress": "100 MAIN ST, TEST, MN, 55000", "coordinates": {"x": -93.1, "y": 45.1}}]}},
        {"code": "Ok", "routes": [{"distance": str(meters), "duration": "1800"}]},
    ])
    result = calculate_driving_mileage("100 Main St, Test, MN 55000", client=client)
    assert result["miles"] == "12.4"
    assert result["duration_minutes"] == "30.0"
    assert result["geocoder"] == "US Census Geocoder Public_AR_Current"
    assert result["origin"]["label"].startswith("Rogers")
    assert client.calls[1][0].endswith("-93.5524563,45.1888596;-93.1,45.1")


def test_nominatim_is_a_fallback_and_result_is_cached():
    address = "Unique fallback address 987654, Minnesota"
    client = FakeClient([
        {"result": {"addressMatches": []}},
        [{"lat": "45.2", "lon": "-93.2", "display_name": "Fallback Match", "licence": "OSM attribution"}],
        {"code": "Ok", "routes": [{"distance": "1609.344", "duration": "60"}]},
    ])
    first = calculate_driving_mileage(address, client=client)
    second = calculate_driving_mileage(address, client=FakeClient([]))
    assert first["miles"] == "1.0" and first["geocoder"].startswith("OpenStreetMap")
    assert second["cache_hit"] is True and second["miles"] == "1.0"


def test_incomplete_address_is_rejected_without_a_request():
    with pytest.raises(MileageError, match="complete job address"):
        calculate_driving_mileage("Rogers", client=FakeClient([]))

