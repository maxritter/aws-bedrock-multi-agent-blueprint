from typing import Any, Dict, List, Optional, Tuple

import requests
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    InternalServerError,
)
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim
from models.trial import Location, LocationContact

logger = Logger()

MAX_RESPONSE_SIZE = 24 * 1024  # 24KB limit for responses


def fetch(url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        with requests.get(url, params=params) as response:
            if response.status_code == 200:
                text = response.text
                try:
                    data = requests.get(url, params=params).json()
                    if isinstance(data, dict):
                        return data
                    logger.error("API response is not a dictionary")
                    return None
                except requests.exceptions.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON: {text[:200]}...")
                    raise
            else:
                logger.error(f"HTTP Error: {response.status_code}")
                logger.error(f"Response text: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error in fetch: {str(e)}")
        return None


def get_nested_value(obj: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    try:
        current: Any = obj
        for key in path:
            if current is None:
                return default
            current = current.get(key)
        return current if current is not None else default
    except (KeyError, TypeError, AttributeError):
        return default


def get_first_item(obj: Dict[str, Any], path: List[str], field: Optional[str] = None) -> Any:
    try:
        items = get_nested_value(obj, path, [])
        if items and isinstance(items, list):
            if field:
                return items[0].get(field)
            return items[0]
        return None
    except (IndexError, AttributeError):
        return None


def get_collaborators(study: Dict[str, Any]) -> Optional[str]:
    try:
        collaborators = get_nested_value(study, ["protocolSection", "sponsorCollaboratorsModule", "collaborators"], [])
        return "|".join(collab.get("name", "") for collab in collaborators if collab.get("name"))
    except Exception:
        return None


def truncate_response(text: str) -> str:
    """Truncate response to stay within size limit while maintaining readability."""
    if not text or len(text.encode("utf-8")) <= MAX_RESPONSE_SIZE:
        return text
    lines = text.split("\n")
    result = []
    current_size = 0

    for line in lines:
        line_size = len((line + "\n").encode("utf-8"))
        if current_size + line_size > MAX_RESPONSE_SIZE:
            result.append("... (Response truncated due to size limit)")
            break
        result.append(line)
        current_size += line_size

    return "\n".join(result)


def process_location_contacts(contacts: List[Dict[str, Any]]) -> List[LocationContact]:
    if not contacts:
        return []
    return [
        LocationContact(
            name=contact.get("name"),
            role=contact.get("role"),
            phone=contact.get("phone"),
            phone_ext=contact.get("phoneExt"),
            email=contact.get("email"),
        )
        for contact in contacts
    ]


def process_locations(study: Dict[str, Any]) -> List[Location]:
    locations_data = get_nested_value(study, ["protocolSection", "contactsLocationsModule", "locations"], [])
    if not locations_data:
        return []

    return [
        Location(
            facility=loc.get("facility"),
            status=loc.get("status"),
            city=loc.get("city"),
            state=loc.get("state"),
            zip=loc.get("zip"),
            country=loc.get("country"),
            country_code=loc.get("countryCode"),
            contacts=process_location_contacts(loc.get("contacts", [])),
            geo_point=loc.get("geoPoint"),
        )
        for loc in locations_data
    ]


def geocode_address(
    city: Optional[str], state: Optional[str], zip_code: Optional[str], country: Optional[str]
) -> Tuple[float, float]:
    """Convert address components to latitude and longitude."""
    if not any([city, state, zip_code, country]):
        raise BadRequestError("At least one location parameter (city, state, zip, or country) must be provided")

    address_parts = []
    if city:
        address_parts.append(city)
    if state:
        address_parts.append(state)
    if zip_code:
        address_parts.append(zip_code)
    if country:
        address_parts.append(country)

    address = ", ".join(address_parts)

    try:
        geolocator = Nominatim(user_agent="clinical_trials_app")
        location = geolocator.geocode(address)

        if location is None:
            raise BadRequestError(f"Could not geocode address: {address}")

        return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        logger.error(f"Geocoding error: {str(e)}")
        raise InternalServerError("Geocoding service unavailable")


def calculate_closest_location(
    locations: List[Location], user_lat: float, user_lon: float, max_distance: Optional[float] = None
) -> Optional[Tuple[float, Location]]:
    """Calculate the closest location from a list of locations to the user's coordinates."""
    closest_distance = float("inf")
    closest_loc = None

    for location in locations:
        if not location.geo_point:
            continue

        loc_lat = location.geo_point.get("lat")
        loc_lon = location.geo_point.get("lon")

        if loc_lat is None or loc_lon is None:
            continue

        distance = geodesic((user_lat, user_lon), (loc_lat, loc_lon)).kilometers

        if distance < closest_distance:
            closest_distance = distance
            closest_loc = location

    if closest_loc and (max_distance is None or closest_distance <= max_distance):
        return closest_distance, closest_loc

    return None
