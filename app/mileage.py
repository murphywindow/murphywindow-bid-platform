"""Address geocoding and driving-distance calculation with persisted lineage."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from copy import deepcopy
import hashlib
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
    "origin_label": "Rogers, Minnesota 55374 city center",
    "origin_latitude": "45.1888596",
    "origin_longitude": "-93.5524563",
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


def _request_json(client: httpx.Client, url: str, **kwargs: Any) -> Any:
    try:
        response = client.get(url, timeout=12.0, **kwargs)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MileageError(f"Mapping service request failed: {exc}") from exc


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
        label = str(match.get("matchedAddress") or address)
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
        label = str(match.get("display_name") or address)
        results.append({
            "id": _address_id(provider, label, latitude, longitude),
            "label": label, "matched_address": label,
            "street": street, "city": str(city),
            "state": str(details.get("state") or ""),
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
            results = _search_nominatim(active_client, normalized, active_limit)
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


def calculate_driving_mileage(address: str, settings: dict | None = None, *, client: httpx.Client | None = None) -> dict:
    """Geocode one job address and return fastest-route mileage from configured Rogers origin."""
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
        destination = _geocode(active_client, query)
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
