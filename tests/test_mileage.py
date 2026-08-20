from decimal import Decimal

import httpx
import pytest

from app.mileage import MileageError, calculate_driving_mileage, search_addresses


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


class ConnectionBlockedClient:
    def get(self, url, **kwargs):
        request = httpx.Request("GET", url)
        raise httpx.ConnectError("[WinError 10013] forbidden socket access", request=request)


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


def test_address_search_returns_structured_census_results_and_echoes_request_id():
    query = "321 Unique Census Search Avenue, Rogers MN"
    client = FakeClient([{"result": {"addressMatches": [{
        "matchedAddress": "321 UNIQUE CENSUS SEARCH AVE, ROGERS, MN, 55374",
        "coordinates": {"x": -93.55, "y": 45.18},
        "addressComponents": {
            "fromAddress": "321", "streetName": "UNIQUE CENSUS SEARCH",
            "suffixType": "AVE", "city": "ROGERS", "state": "MN",
            "zip": "55374", "county": "Hennepin",
        },
    }]}}])
    result = search_addresses(query, limit=5, request_id="request-new", client=client)
    assert result["request_id"] == "request-new"
    assert result["cache_hit"] is False
    assert result["provider"].startswith("US Census")
    assert result["results"] == [{
        "id": result["results"][0]["id"],
        "label": "321 Unique Census Search Ave., Rogers, MN 55374",
        "matched_address": "321 Unique Census Search Ave., Rogers, MN 55374",
        "street": "321 UNIQUE CENSUS SEARCH AVE", "city": "ROGERS",
        "state": "MN", "zip": "55374", "county": "Hennepin",
        "latitude": "45.18", "longitude": "-93.55",
        "provider": "US Census Geocoder Public_AR_Current", "attribution": None,
    }]
    assert client.calls[0][1]["params"]["benchmark"] == "Public_AR_Current"

    # A cached response echoes the current request token rather than retaining
    # an older token; callers can safely reject out-of-order responses.
    cached = search_addresses(query, limit=5, request_id="request-latest", client=FakeClient([]))
    assert cached["cache_hit"] is True
    assert cached["request_id"] == "request-latest"


def test_address_search_falls_back_to_structured_nominatim_and_keeps_attribution(monkeypatch):
    monkeypatch.setattr("app.mileage._LAST_NOMINATIM_REQUEST", 0.0)
    client = FakeClient([
        {"result": {"addressMatches": []}},
        [{
            "lat": "45.2000", "lon": "-93.2000",
            "display_name": "45 Example Road, Elk River, Minnesota 55330, United States",
            "licence": "OpenStreetMap contributors",
            "address": {
                "house_number": "45", "road": "Example Road", "city": "Elk River",
                "state": "Minnesota", "postcode": "55330", "county": "Sherburne County",
            },
        }],
    ])
    result = search_addresses(
        "45 Unique Nominatim Example Road", limit=3, request_id="fallback", client=client
    )
    row = result["results"][0]
    assert row["street"] == "45 Example Road"
    assert row["label"] == "45 Example Rd., Elk River, MN 55330"
    assert "United States" not in row["matched_address"]
    assert row["city"] == "Elk River" and row["county"] == "Sherburne County"
    assert result["attribution"] == "OpenStreetMap contributors"
    assert client.calls[1][1]["params"]["addressdetails"] == 1
    assert client.calls[1][1]["params"]["limit"] == 3


def test_address_search_short_query_fails_without_request_and_no_match_is_non_destructive():
    with pytest.raises(MileageError, match="at least three"):
        search_addresses("MN", client=FakeClient([]))
    no_match = search_addresses(
        "No Such Unique Address Search 112233", request_id="none",
        client=FakeClient([{"result": {"addressMatches": []}}, []]),
    )
    assert no_match["results"] == []
    assert no_match["request_id"] == "none"


def test_mapping_connection_failure_is_actionable_and_does_not_leak_socket_details(monkeypatch):
    monkeypatch.setattr("app.mileage._LAST_NOMINATIM_REQUEST", 0.0)
    with pytest.raises(MileageError) as caught:
        search_addresses(
            "500 Network Test Avenue, Rogers, MN 55374",
            client=ConnectionBlockedClient(),
        )
    message = str(caught.value)
    assert "cannot reach the mapping providers" in message
    assert "network or firewall" in message
    assert "WinError" not in message
    assert "10013" not in message


def test_address_search_formats_unit_city_state_and_zip_without_destination_or_county():
    query = "3900 Hoffman Rd., Apt 6, White Bear Lake, MN 55110"
    client = FakeClient([{"result": {"addressMatches": [{
        "matchedAddress": "3900 HOFFMAN RD, WHITE BEAR LAKE, MN, 55110",
        "coordinates": {"x": -93.02, "y": 45.05},
        "addressComponents": {
            "fromAddress": "3900", "streetName": "HOFFMAN", "suffixType": "RD",
            "city": "WHITE BEAR LAKE", "state": "MN", "zip": "55110",
            "county": "Ramsey County",
        },
    }]}}])
    result = search_addresses(query, client=client)
    assert result["results"][0]["label"] == "3900 Hoffman Rd., Apt 6, White Bear Lake, MN 55110"


def test_landmark_search_removes_provider_sensitive_filler_words(monkeypatch):
    monkeypatch.setattr("app.mileage._LAST_NOMINATIM_REQUEST", 0.0)
    client = FakeClient([
        {"result": {"addressMatches": []}},
        [{
            "lat": "46.8208", "lon": "-100.7827",
            "name": "North Dakota Capitol Building",
            "display_name": "North Dakota Capitol Building, North 4th Street, Bismarck, North Dakota, 58502, United States",
            "address": {"road": "North 4th Street", "city": "Bismarck", "state": "North Dakota", "postcode": "58502"},
        }],
    ])
    result = search_addresses("North Dakota State Capitol", client=client)
    assert client.calls[1][1]["params"]["q"] == "North Dakota Capitol"
    assert result["results"][0]["label"] == "North Dakota Capitol Building, North 4th St., Bismarck, ND 58502"


def test_address_search_deduplicates_provider_objects_with_the_same_postal_label(monkeypatch):
    monkeypatch.setattr("app.mileage._LAST_NOMINATIM_REQUEST", 0.0)
    duplicate = {
        "lat": "45.060", "lon": "-93.030", "display_name": "Hoffman Road, White Bear Lake",
        "address": {"road": "Hoffman Road", "city": "White Bear Lake", "state": "Minnesota", "postcode": "55110"},
    }
    client = FakeClient([{"result": {"addressMatches": []}}, [duplicate, {**duplicate, "lat": "45.061"}]])
    result = search_addresses("Hoffman Road White Bear Lake unique dedupe", client=client)
    assert [row["label"] for row in result["results"]] == ["Hoffman Rd., White Bear Lake, MN 55110"]
    assert result["results"][0]["state"] == "MN"
