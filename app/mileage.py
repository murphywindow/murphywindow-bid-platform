"""Address geocoding and driving-distance calculation with persisted lineage."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from copy import deepcopy
import hashlib
import re
from threading import Lock
import time
from typing import Any

import httpx

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
METERS_PER_MILE = Decimal("1609.344")
USER_AGENT = "MurphyWindowBidPlatform/1.0 (local estimating mileage lookup)"

DEFAULT_SETTINGS = {
    "origin_label": "Minneapolis, Minnesota city center",
    "origin_latitude": "44.9778",
    "origin_longitude": "-93.2650",
    "origin_status": "owner_requested_city_origin_configurable",
    "geocoder_primary": "US Census Geocoder Public_AR_Current",
    "geocoder_fallback": "OpenStreetMap Nominatim public service",
    "router": "OSRM public routing service",
    "online_required": True,
    "rounding": "nearest 0.1 mile, ROUND_HALF_UP",
}


class MileageError(ValueError):
    pass


_CACHE: dict[str, dict] = {}
_ADDRESS_SEARCH_CACHE: dict[str, dict] = {}
_CACHE_LOCK = Lock()
_NOMINATIM_LOCK = Lock()
_LAST_NOMINATIM_REQUEST = 0.0

_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
_STREET_SUFFIXES = {
    "avenue": "Ave.", "ave": "Ave.", "boulevard": "Blvd.", "blvd": "Blvd.",
    "circle": "Cir.", "court": "Ct.", "ct": "Ct.", "drive": "Dr.", "dr": "Dr.",
    "highway": "Hwy.", "lane": "Ln.", "ln": "Ln.", "parkway": "Pkwy.", "pkwy": "Pkwy.",
    "place": "Pl.", "pl": "Pl.", "road": "Rd.", "rd": "Rd.", "street": "St.", "st": "St.",
    "terrace": "Ter.", "trail": "Trl.", "way": "Way",
}


def _display_address(value: Any) -> str:
    """Keep U.S.-only suggestions concise without altering provider coordinates."""
    label = str(value or "").strip()
    return re.sub(r",\s*(?:United States(?: of America)?|USA|US)\s*$", "", label, flags=re.IGNORECASE)


def _title_words(value: Any) -> str:
    return " ".join(word if word.isupper() and len(word) <= 3 else word.capitalize() for word in str(value or "").split())


def _postal_label(
    street: Any, city: Any, state: Any, postal_code: Any, *, query: str = "",
    location_name: Any = "",
) -> str:
    """Build one compact estimator-facing postal address from provider fields."""
    raw_street = str(street or "").strip()
    street_text = _title_words(street)
    words = street_text.split()
    if words:
        suffix_key = words[-1].rstrip(".").casefold()
        if suffix_key in _STREET_SUFFIXES:
            words[-1] = _STREET_SUFFIXES[suffix_key]
        street_text = " ".join(words)
    unit_match = re.search(r"(?:,|\s)\s*(?:apt\.?|apartment|unit|#)\s*[-#]?\s*([A-Za-z0-9-]+)", query, re.IGNORECASE)
    if unit_match and street_text and not re.search(r"\b(?:apt\.?|unit|#)\b", street_text, re.IGNORECASE):
        street_text = f"{street_text}, Apt {unit_match.group(1)}"
    state_text = str(state or "").strip()
    state_text = _STATE_CODES.get(state_text.casefold(), state_text.upper())
    locality = ", ".join(part for part in (_title_words(city), " ".join(part for part in (state_text, str(postal_code or "").strip()) if part)) if part)
    address = ", ".join(part for part in (street_text, locality) if part).strip(" ,")
    name = str(location_name or "").strip(" ,")
    normalized_name = re.sub(r"[^a-z0-9]", "", name.casefold())
    street_names = {
        re.sub(r"[^a-z0-9]", "", value.casefold())
        for value in (raw_street, street_text) if value
    }
    if name and normalized_name not in street_names:
        return f"{name}, {address}" if address else name
    return address


def _tolerant_landmark_query(query: str) -> str:
    # Providers often index the proper name without generic institutional words.
    simplified = re.sub(r"\b(?:the|state|building|complex|campus|facility)\b", " ", query, flags=re.IGNORECASE)
    return " ".join(simplified.split()) or query


def _request_json(client: httpx.Client, url: str, **kwargs: Any) -> Any:
    try:
        response = client.get(url, timeout=12.0, **kwargs)
        response.raise_for_status()
        return response.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        # Never expose socket, proxy, or firewall details in the estimator UI.
        # The chained exception remains available to server-side diagnostics.
        raise MileageError(
            "Live address search cannot reach the mapping providers. "
            "Check the server's network or firewall access and try again."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise MileageError(
            "The mapping provider returned an error. Try again shortly."
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise MileageError(
            "The mapping provider returned an unreadable response. Try again shortly."
        ) from exc


def _geocode_census(client: httpx.Client, address: str) -> dict | None:
    results = _search_census(client, address, 1)
    return results[0] if results else None


def _address_id(provider: str, label: str, latitude: str, longitude: str) -> str:
    basis = "|".join((provider, label, latitude, longitude)).encode("utf-8")
    return "addr_" + hashlib.sha256(basis).hexdigest()[:24]


def _search_census(client: httpx.Client, address: str, limit: int) -> list[dict]:
    payload = _request_json(client, CENSUS_URL, params={"address": address, "benchmark": "Public_AR_Current", "format": "json"})
    matches = payload.get("result", {}).get("addressMatches", []) if isinstance(payload, dict) else []
    results = []
    provider = "US Census Geocoder Public_AR_Current"
    for match in matches[:limit]:
        coordinates = match.get("coordinates", {})
        if coordinates.get("x") is None or coordinates.get("y") is None:
            continue
        components = match.get("addressComponents") or {}
        house = str(components.get("fromAddress") or components.get("houseNumber") or "").strip()
        street_parts = [
            house,
            components.get("preDirection"),
            components.get("streetName"),
            components.get("suffixType"),
            components.get("suffixDirection"),
        ]
        street = " ".join(str(part).strip() for part in street_parts if part)
        latitude, longitude = str(coordinates["y"]), str(coordinates["x"])
        label = _postal_label(street, components.get("city"), components.get("state"), components.get("zip"), query=address)
        if not label:
            label = _display_address(match.get("matchedAddress") or address)
        results.append({
            "id": _address_id(provider, label, latitude, longitude),
            "label": label, "matched_address": label,
            "street": street, "city": str(components.get("city") or ""),
            "state": str(components.get("state") or ""),
            "zip": str(components.get("zip") or ""),
            "county": str(components.get("county") or ""),
            "latitude": latitude, "longitude": longitude,
            "provider": provider, "attribution": None,
        })
    return results


def _geocode_nominatim(client: httpx.Client, address: str) -> dict | None:
    results = _search_nominatim(client, address, 1)
    return results[0] if results else None


def _search_nominatim(client: httpx.Client, address: str, limit: int) -> list[dict]:
    global _LAST_NOMINATIM_REQUEST
    # Public-service policy permits at most one request/second; the lock also
    # prevents concurrent local tabs from exceeding that limit.
    with _NOMINATIM_LOCK:
        remaining = 1.0 - (time.monotonic() - _LAST_NOMINATIM_REQUEST)
        if remaining > 0:
            time.sleep(remaining)
        payload = _request_json(
            client, NOMINATIM_URL,
            params={"q": address, "format": "jsonv2", "limit": limit, "countrycodes": "us", "addressdetails": 1},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en"},
        )
        _LAST_NOMINATIM_REQUEST = time.monotonic()
    if not isinstance(payload, list):
        return []
    provider = "OpenStreetMap Nominatim public service"
    results = []
    for match in payload[:limit]:
        if match.get("lat") is None or match.get("lon") is None:
            continue
        details = match.get("address") or {}
        road = next((details.get(key) for key in (
            "road", "pedestrian", "residential", "footway", "path"
        ) if details.get(key)), "")
        street = " ".join(part for part in (str(details.get("house_number") or "").strip(), str(road).strip()) if part)
        city = next((details.get(key) for key in (
            "city", "town", "village", "municipality", "hamlet"
        ) if details.get(key)), "")
        latitude, longitude = str(match["lat"]), str(match["lon"])
        display_name = _display_address(match.get("display_name") or "")
        first_component = display_name.split(",", 1)[0].strip()
        location_name = match.get("name") or first_component
        label = _postal_label(
            street, city, details.get("state"), details.get("postcode"),
            query=address, location_name=location_name,
        )
        if not label:
            label = _display_address(match.get("display_name") or address)
        state = str(details.get("state") or "").strip()
        state = _STATE_CODES.get(state.casefold(), state.upper())
        results.append({
            "id": _address_id(provider, label, latitude, longitude),
            "label": label, "matched_address": label,
            "street": street, "city": str(city),
            "state": state,
            "zip": str(details.get("postcode") or ""),
            "county": str(details.get("county") or ""),
            "latitude": latitude, "longitude": longitude,
            "provider": provider, "attribution": match.get("licence"),
        })
    return results


def search_addresses(
    query: str,
    *,
    limit: int = 5,
    request_id: str | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Return structured address suggestions using the mileage geocoders.

    The request identifier is echoed, never stored as global "latest" state, so
    an API/client can discard a response that belongs to an older query. Cached
    payloads are copied before return to prevent one caller from mutating a
    later response.
    """
    normalized = " ".join(str(query or "").split())
    if len(normalized) < 3:
        raise MileageError("Enter at least three address characters before searching.")
    active_limit = max(1, min(int(limit), 10))
    cache_key = f"{normalized.casefold()}|{active_limit}"
    with _CACHE_LOCK:
        cached = deepcopy(_ADDRESS_SEARCH_CACHE.get(cache_key))
    if cached is not None:
        return {**cached, "request_id": request_id, "cache_hit": True}

    owns_client = client is None
    active_client = client or httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        try:
            results = _search_census(active_client, normalized, active_limit)
        except MileageError:
            results = []
        if not results:
            results = _search_nominatim(active_client, _tolerant_landmark_query(normalized), active_limit)
        # Nominatim can return multiple OSM objects for the same building or
        # street. Once formatted for estimators those are one choice, not
        # several indistinguishable rows.
        unique_results = []
        seen_labels = set()
        for item in results:
            key = re.sub(r"[^a-z0-9]", "", str(item.get("label") or "").casefold())
            if not key or key in seen_labels:
                continue
            seen_labels.add(key)
            unique_results.append(item)
        results = unique_results[:active_limit]
        provider = results[0]["provider"] if results else None
        attribution = next((item.get("attribution") for item in results if item.get("attribution")), None)
        payload = {
            "query": normalized, "results": results, "provider": provider,
            "attribution": attribution, "cache_hit": False,
        }
        with _CACHE_LOCK:
            _ADDRESS_SEARCH_CACHE[cache_key] = deepcopy(payload)
        return {**payload, "request_id": request_id}
    finally:
        if owns_client:
            active_client.close()


def _geocode(client: httpx.Client, address: str) -> dict:
    try:
        result = _geocode_census(client, address)
    except MileageError:
        result = None
    if result is None:
        result = _geocode_nominatim(client, address)
    if result is None:
        raise MileageError("No mapping match was found. Enter a complete U.S. street address, city, state, and ZIP, then try again.")
    return result


def calculate_driving_mileage(
    address: str, settings: dict | None = None, *, client: httpx.Client | None = None,
    destination: dict | None = None,
) -> dict:
    """Geocode one job address and return fastest-route mileage from the configured Minneapolis origin."""
    query = " ".join(str(address or "").split())
    if len(query) < 8:
        raise MileageError("Enter a complete job address before calculating drive mileage.")
    cfg = {**DEFAULT_SETTINGS, **(settings or {})}
    cache_key = "|".join([query.lower(), str(cfg["origin_latitude"]), str(cfg["origin_longitude"])])
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
    if cached:
        return {**cached, "cache_hit": True}

    owns_client = client is None
    active_client = client or httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        destination = destination or _geocode(active_client, query)
        origin_lon, origin_lat = str(cfg["origin_longitude"]), str(cfg["origin_latitude"])
        destination_lon, destination_lat = destination["longitude"], destination["latitude"]
        route_url = f"{OSRM_URL}/{origin_lon},{origin_lat};{destination_lon},{destination_lat}"
        route_payload = _request_json(active_client, route_url, params={"overview": "false", "alternatives": "false", "steps": "false"})
        routes = route_payload.get("routes", []) if isinstance(route_payload, dict) else []
        if route_payload.get("code") != "Ok" or not routes:
            raise MileageError("The address was found, but no driving route was returned.")
        meters = Decimal(str(routes[0]["distance"]))
        seconds = Decimal(str(routes[0].get("duration", 0)))
        miles = (meters / METERS_PER_MILE).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        minutes = (seconds / Decimal("60")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        result = {
            "input_address": query, "matched_address": destination["matched_address"],
            "miles": str(miles), "distance_meters": str(meters), "duration_minutes": str(minutes),
            "origin": {"label": cfg["origin_label"], "latitude": origin_lat, "longitude": origin_lon, "status": cfg.get("origin_status")},
            "destination": {"latitude": destination_lat, "longitude": destination_lon},
            "geocoder": destination["provider"], "router": cfg["router"], "attribution": destination.get("attribution"),
            "calculated_at": datetime.now(UTC).isoformat(), "rounding": cfg["rounding"], "cache_hit": False,
        }
        with _CACHE_LOCK:
            _CACHE[cache_key] = result
        return result
    finally:
        if owns_client:
            active_client.close()
