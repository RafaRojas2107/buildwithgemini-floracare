# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tools for the FloraCare Assistant, backed by Google Cloud Firestore."""

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from google.cloud import firestore, storage
from google.adk.tools import ToolContext

# Load environment variables from .env
load_dotenv()

# Explicitly pin project ID and bucket name as strings per Agent Platform requirements
FIRESTORE_PROJECT = "qwiklabs-gcp-03-c2254edad736"
PLANTS_COLLECTION = "plants"
IMAGE_BUCKET_NAME = "floracare-images-fbb32859"


def _get_db() -> firestore.Client:
    """Get Firestore client pinned explicitly to the project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT)


def _slugify(text: str) -> str:
    """Convert plant name into a clean document ID slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text).strip("-")


# ============================================================================
# FloraCare Firestore Tools (Read & Write)
# ============================================================================


def search_plant_catalog(
    query: str = "",
    light_preference: str = "",
    care_difficulty: str = "",
) -> List[Dict[str, Any]]:
    """Searches the Firestore plant catalog by name, light requirements, or difficulty.

    Args:
        query: Optional plant name or keyword to search for (case-insensitive).
        light_preference: Optional light filter (e.g., 'low', 'medium', 'bright').
        care_difficulty: Optional difficulty filter (e.g., 'easy', 'moderate').

    Returns:
        A list of matching plant records from Firestore.
    """
    db = _get_db()
    docs = db.collection(PLANTS_COLLECTION).stream()
    results: List[Dict[str, Any]] = []

    q_lower = query.lower().strip()
    light_lower = light_preference.lower().strip()
    diff_lower = care_difficulty.lower().strip()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        # Name / keyword filter
        if q_lower:
            name_match = q_lower in data.get("name", "").lower()
            sci_match = q_lower in data.get("scientific_name", "").lower()
            notes_match = q_lower in data.get("care_notes", "").lower()
            if not (name_match or sci_match or notes_match):
                continue

        # Light filter
        if light_lower:
            plant_light = data.get("light_requirement", "").lower()
            if light_lower not in plant_light:
                continue

        # Difficulty filter
        if diff_lower:
            plant_diff = data.get("care_difficulty", "").lower()
            if diff_lower not in plant_diff:
                continue

        results.append(data)

    return results


def lookup_plant_care(plant_name: str) -> Dict[str, Any]:
    """Retrieves full care instructions and requirements for a specific plant from Firestore.

    Args:
        plant_name: Common or botanical name of the plant (e.g., 'Monstera Deliciosa', 'Snake Plant').

    Returns:
        A dictionary with care details, watering schedule, lighting, and toxicity.
    """
    db = _get_db()
    collection = db.collection(PLANTS_COLLECTION)

    # Try direct slug lookup
    slug = _slugify(plant_name)
    doc = collection.document(slug).get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    # Fallback to search query
    matches = search_plant_catalog(query=plant_name)
    if matches:
        return matches[0]

    return {
        "error": f"Plant '{plant_name}' not found in the catalog.",
        "suggestion": "Use search_plant_catalog to see available plants or add_plant_to_catalog to register it.",
    }


def check_watering_schedule(
    plant_name: str,
    days_since_last_watered: int,
    light_level: str = "medium",
) -> Dict[str, Any]:
    """Calculates if a plant needs water and when to water next based on Firestore data.

    Args:
        plant_name: The plant name (e.g., 'Monstera Deliciosa').
        days_since_last_watered: Number of days elapsed since the plant was last watered.
        light_level: Current home lighting conditions ('low', 'medium', or 'bright').

    Returns:
        A dictionary with watering assessment, days remaining, and guidance.
    """
    plant = lookup_plant_care(plant_name)
    if "error" in plant:
        return plant

    base_freq = plant.get("watering_frequency_days", 7)
    light_normalized = light_level.lower().strip()

    # Adjust interval based on light conditions:
    # - Low light slows transpiration and soil drying (needs ~20% more days between waterings)
    # - Bright light speeds drying (needs ~15% fewer days)
    adjustment = 0
    if "low" in light_normalized:
        adjustment = max(1, round(base_freq * 0.2))
    elif "bright" in light_normalized:
        adjustment = -max(1, round(base_freq * 0.15))

    adjusted_freq = max(3, base_freq + adjustment)
    days_until_next = adjusted_freq - days_since_last_watered
    needs_watering_now = days_until_next <= 0

    if needs_watering_now:
        recommendation = (
            f"Yes, your {plant.get('name')} is due for watering! "
            f"It was last watered {days_since_last_watered} days ago (normal interval: {adjusted_freq} days). "
            f"Check if the top 2-3 inches of soil are dry before watering thoroughly."
        )
    else:
        recommendation = (
            f"Not yet. Your {plant.get('name')} should be watered in approximately {days_until_next} day(s). "
            f"With {light_level} light, the optimal watering interval is every {adjusted_freq} days."
        )

    return {
        "plant_name": plant.get("name"),
        "scientific_name": plant.get("scientific_name"),
        "days_since_last_watered": days_since_last_watered,
        "base_interval_days": base_freq,
        "adjusted_interval_days": adjusted_freq,
        "days_until_next_watering": max(0, days_until_next),
        "needs_watering_now": needs_watering_now,
        "light_level_considered": light_level,
        "watering_instructions": plant.get("watering_instructions"),
        "recommendation": recommendation,
    }


def add_plant_to_catalog(
    name: str,
    scientific_name: str,
    watering_frequency_days: int,
    light_requirement: str,
    care_difficulty: str,
    watering_instructions: str,
    humidity: str = "moderate (40-60%)",
    toxicity: str = "non-toxic",
    care_notes: str = "",
) -> Dict[str, Any]:
    """Adds a new house plant to the Firestore plant catalog (Write tool).

    Args:
        name: Common name of the plant (e.g., 'Spider Plant').
        scientific_name: Botanical name (e.g., 'Chlorophytum comosum').
        watering_frequency_days: Recommended interval between waterings in days.
        light_requirement: Lighting requirement (e.g., 'bright indirect light').
        care_difficulty: Difficulty level ('easy', 'moderate', or 'advanced').
        watering_instructions: Detailed soil moisture guidance.
        humidity: Preferred humidity range.
        toxicity: Pet toxicity information.
        care_notes: Additional growing tips or notes.

    Returns:
        A dictionary confirming the newly created plant record in Firestore.
    """
    if watering_frequency_days <= 0:
        return {"error": "watering_frequency_days must be a positive integer."}

    doc_id = _slugify(name)
    record = {
        "id": doc_id,
        "name": name.strip(),
        "scientific_name": scientific_name.strip(),
        "watering_frequency_days": int(watering_frequency_days),
        "light_requirement": light_requirement.strip(),
        "care_difficulty": care_difficulty.strip().lower(),
        "watering_instructions": watering_instructions.strip(),
        "humidity": humidity.strip(),
        "toxicity": toxicity.strip(),
        "last_watered_date": None,
        "care_notes": care_notes.strip(),
    }

    db = _get_db()
    db.collection(PLANTS_COLLECTION).document(doc_id).set(record)

    return {
        "status": "success",
        "message": f"Successfully added '{name}' to Firestore catalog.",
        "plant": record,
    }


def record_plant_watering(
    plant_name: str,
    watering_date: Optional[str] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Records that a plant was watered and updates Firestore (Write tool).

    Args:
        plant_name: Name of the plant to update.
        watering_date: Date watered (YYYY-MM-DD). If omitted, uses today's date.
        notes: Optional care notes to log with this watering.

    Returns:
        A dictionary confirming the update in Firestore.
    """
    plant = lookup_plant_care(plant_name)
    if "error" in plant:
        return plant

    doc_id = plant.get("id")
    if not doc_id:
        doc_id = _slugify(plant_name)

    effective_date = watering_date or datetime.date.today().isoformat()

    updates: Dict[str, Any] = {"last_watered_date": effective_date}
    if notes:
        existing_notes = plant.get("care_notes", "")
        updated_notes = f"{existing_notes} [{effective_date}: {notes}]".strip()
        updates["care_notes"] = updated_notes

    db = _get_db()
    db.collection(PLANTS_COLLECTION).document(doc_id).update(updates)

    return {
        "status": "success",
        "message": f"Recorded watering for '{plant.get('name')}' on {effective_date}.",
        "plant_id": doc_id,
        "last_watered_date": effective_date,
    }


def lookup_botanical_taxonomy(
    plant_name: str,
) -> Dict[str, Any]:
    """Fetches real botanical taxonomy and scientific classification from the Global Biodiversity Information Facility (GBIF) open API.

    Args:
        plant_name: Scientific, botanical, or common name of the plant (e.g., 'Monstera deliciosa', 'Ficus lyrata', 'Epipremnum aureum').

    Returns:
        A dictionary with real botanical classification including family, genus, species, kingdom, status, and rank.
    """
    base_url = os.environ.get("GBIF_API_URL", "https://api.gbif.org/v1/species/match")
    params = urllib.parse.urlencode({"name": plant_name.strip()})
    url = f"{base_url}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FloraCareAgent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get("matchType") == "NONE":
                return {
                    "found": False,
                    "query": plant_name,
                    "message": f"No botanical taxonomy match found for '{plant_name}'.",
                }
            return {
                "found": True,
                "query": plant_name,
                "canonical_name": data.get("canonicalName"),
                "scientific_name": data.get("scientificName"),
                "kingdom": data.get("kingdom"),
                "phylum": data.get("phylum"),
                "order": data.get("order"),
                "family": data.get("family"),
                "genus": data.get("genus"),
                "species": data.get("species"),
                "rank": data.get("rank"),
                "status": data.get("status"),
                "confidence": data.get("confidence"),
            }
    except Exception as e:
        return {"error": f"Failed to fetch botanical taxonomy from GBIF: {str(e)}"}


def get_local_plant_climate(
    location: str,
) -> Dict[str, Any]:
    """Fetches real-time temperature and relative humidity from the Open-Meteo public API to advise on house plant humidity and watering adjustments.

    Args:
        location: City or location name (e.g., 'Austin', 'Seattle', 'Chicago', 'New York').

    Returns:
        A dictionary containing location, current temperature, relative humidity percentage, and a plant care climate advisory.
    """
    # 1. Geocode location name
    geo_base = os.environ.get(
        "OPEN_METEO_GEO_URL", "https://geocoding-api.open-meteo.com/v1/search"
    )
    geo_params = urllib.parse.urlencode({"name": location.strip(), "count": 1})
    geo_url = f"{geo_base}?{geo_params}"

    try:
        req = urllib.request.Request(
            geo_url, headers={"User-Agent": "FloraCareAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            geo_data = json.loads(resp.read().decode())

        results = geo_data.get("results")
        if not results:
            return {"error": f"Could not find coordinates for location: '{location}'."}

        place = results[0]
        lat = place.get("latitude")
        lon = place.get("longitude")
        place_name = (
            f"{place.get('name')}, {place.get('admin1', '')} {place.get('country', '')}"
        ).strip(", ")

        # 2. Fetch current weather and humidity
        weather_base = os.environ.get(
            "OPEN_METEO_API_URL", "https://api.open-meteo.com/v1/forecast"
        )
        weather_params = urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m",
            }
        )
        weather_url = f"{weather_base}?{weather_params}"

        req_weather = urllib.request.Request(
            weather_url, headers={"User-Agent": "FloraCareAgent/1.0"}
        )
        with urllib.request.urlopen(req_weather, timeout=10) as resp:
            weather_data = json.loads(resp.read().decode())

        current = weather_data.get("current", {})
        temp_c = current.get("temperature_2m")
        temp_f = (
            round((temp_c * 9.0 / 5.0) + 32.0, 1) if temp_c is not None else None
        )
        humidity = current.get("relative_humidity_2m")

        if humidity is not None and humidity < 40:
            advisory = (
                f"Air is relatively dry ({humidity}% RH). Tropical plants like Monsteras, Fiddle Leaf Figs, "
                "and Peace Lilies may benefit from a pebble tray, room humidifier, or light grouping."
            )
        elif humidity is not None and humidity > 70:
            advisory = (
                f"Air is very humid ({humidity}% RH). Soil will dry out slower; ensure good ventilation "
                "and check that the top soil is dry before watering."
            )
        else:
            advisory = (
                f"Moderate humidity ({humidity}% RH). Ideal for most general indoor house plants."
            )

        return {
            "location": place_name,
            "latitude": lat,
            "longitude": lon,
            "temperature_celsius": temp_c,
            "temperature_fahrenheit": temp_f,
            "relative_humidity_percentage": humidity,
            "climate_advisory": advisory,
        }
    except Exception as e:
        return {"error": f"Failed to retrieve weather data from Open-Meteo: {str(e)}"}


def geocode_address(
    address: str,
) -> Dict[str, Any]:
    """Uses Google Maps Geocoding API to convert an address or location name into geographic coordinates.

    Args:
        address: The street address, city, or place name to geocode (e.g., '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        A dictionary containing the formatted address, location coordinates (latitude and longitude), and place ID.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {
            "error": "GOOGLE_MAPS_API_KEY is not configured or is set to placeholder 'PASTE_KEY_HERE'. Please update GOOGLE_MAPS_API_KEY in .env."
        }

    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = urllib.parse.urlencode({"address": address.strip(), "key": api_key})
    url = f"{base_url}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FloraCareAgent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        status = data.get("status")
        if status != "OK":
            err_msg = data.get(
                "error_message", f"Geocoding API returned status: {status}"
            )
            return {"error": err_msg, "status": status}

        results = data.get("results", [])
        if not results:
            return {"error": f"No geocoding results found for address: '{address}'."}

        first = results[0]
        loc = first.get("geometry", {}).get("location", {})
        return {
            "address": first.get("formatted_address"),
            "location": {
                "latitude": loc.get("lat"),
                "longitude": loc.get("lng"),
            },
            "place_id": first.get("place_id"),
        }
    except Exception as e:
        return {"error": f"Failed to call Geocoding API: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "florist",
    radius_meters: float = 5000.0,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Uses the Google Places API (New) nearby search to find nearby places of a specific type (e.g., plant nurseries, florists).

    Args:
        latitude: Latitude coordinate of search center point.
        longitude: Longitude coordinate of search center point.
        place_type: Type of place to search for (e.g., 'florist', 'home_goods_store', 'store', 'park').
        radius_meters: Radius around coordinates in meters (default: 5000 meters / 5km).
        max_results: Maximum number of results to return (1-20, default: 5).

    Returns:
        A dictionary containing a list of nearby places with name, address, and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {
            "error": "GOOGLE_MAPS_API_KEY is not configured or is set to placeholder 'PASTE_KEY_HERE'. Please update GOOGLE_MAPS_API_KEY in .env."
        }

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type.strip().lower()],
        "maxResultCount": min(max(1, int(max_results)), 20),
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data_bytes, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        places_raw = data.get("places", [])
        places_clean = []
        for p in places_raw:
            disp_name = p.get("displayName", {}).get("text", "")
            formatted_addr = p.get("formattedAddress", "")
            loc = p.get("location", {})
            places_clean.append(
                {
                    "name": disp_name,
                    "address": formatted_addr,
                    "location": {
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                    },
                }
            )

        return {
            "search_type": place_type,
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_meters": radius_meters,
            "total_found": len(places_clean),
            "places": places_clean,
        }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"error": f"Places API returned HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"error": f"Failed to call Places API (New): {str(e)}"}


async def generate_plant_image(
    plant_name: str,
    visual_description: str = "",
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Generates an image of a plant or interior plant arrangement using the gemini-3.1-flash-lite-image model in the global region.
    Saves the image to the Playground artifacts panel via tool_context.save_artifact, and uploads the image bytes directly to the public Cloud Storage bucket, returning its public HTTPS URL.

    Args:
        plant_name: Name of the house plant to visualize (e.g., 'Monstera Deliciosa', 'Fiddle Leaf Fig', 'Peace Lily').
        visual_description: Optional additional styling details (e.g., 'in a minimalist ceramic pot on a sunny windowsill').
        tool_context: The ADK ToolContext injected by the agent runtime.

    Returns:
        A dictionary with the public Cloud Storage HTTPS URL, artifact filename, and status.
    """
    prompt = f"A photo of a healthy, vibrant {plant_name.strip()} plant"
    if visual_description:
        prompt += f", {visual_description.strip()}"
    prompt += ". High resolution, soft natural indoor lighting, detailed leaves and textures."

    try:
        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT,
            location="global",
        )
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=[genai_types.Modality.IMAGE],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break

        if not image_bytes:
            return {
                "error": f"No image was generated by gemini-3.1-flash-lite-image for '{plant_name}'."
            }

        slug = _slugify(plant_name)
        ext = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
        artifact_filename = f"{slug}.{ext}"

        # 1. Save with tool_context.save_artifact so it shows in Playground's Artifacts panel
        saved_artifact = False
        if tool_context is not None:
            try:
                artifact_part = genai_types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                )
                await tool_context.save_artifact(
                    filename=artifact_filename,
                    artifact=artifact_part,
                )
                saved_artifact = True
            except Exception:
                saved_artifact = False

        # 2. Upload image bytes directly to public Cloud Storage bucket without writing to local file
        storage_client = storage.Client(project=FIRESTORE_PROJECT)
        bucket = storage_client.bucket(IMAGE_BUCKET_NAME)
        unique_id = uuid.uuid4().hex[:8]
        blob_name = f"plants/{slug}_{unique_id}.{ext}"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{IMAGE_BUCKET_NAME}/{blob_name}"

        return {
            "status": "success",
            "plant_name": plant_name,
            "public_url": public_url,
            "artifact_filename": artifact_filename,
            "artifact_saved": saved_artifact,
            "mime_type": mime_type,
            "message": f"Successfully generated image for '{plant_name}' and published to Cloud Storage.",
        }
    except Exception as e:
        return {"error": f"Failed to generate plant image: {str(e)}"}


# ============================================================================
# Math & Calculation Tools (Preserved for compatibility)
# ============================================================================


def calculate_tip(
    bill_amount: float,
    tip_percentage: float = 18.0,
    split_by: int = 1,
) -> Dict[str, Any]:
    """Calculates the tip amount, total bill, and per-person share."""
    if bill_amount < 0:
        return {"error": "Bill amount cannot be negative."}
    if tip_percentage < 0:
        return {"error": "Tip percentage cannot be negative."}
    if split_by < 1:
        return {"error": "Number of people to split by must be at least 1."}

    tip_amount = round(bill_amount * (tip_percentage / 100.0), 2)
    total_amount = round(bill_amount + tip_amount, 2)
    per_person = round(total_amount / split_by, 2)

    return {
        "bill_amount": round(bill_amount, 2),
        "tip_percentage": tip_percentage,
        "tip_amount": tip_amount,
        "total_amount": total_amount,
        "split_by": split_by,
        "per_person": per_person,
    }


def convert_units(
    value: float,
    from_unit: str,
    to_unit: str,
) -> Dict[str, Any]:
    """Converts a numerical value between compatible measurement units."""
    conversions = {
        ("km", "mi"): lambda v: v * 0.621371,
        ("mi", "km"): lambda v: v / 0.621371,
        ("km", "meters"): lambda v: v * 1000.0,
        ("meters", "km"): lambda v: v / 1000.0,
        ("m", "ft"): lambda v: v * 3.28084,
        ("ft", "m"): lambda v: v / 3.28084,
        ("in", "cm"): lambda v: v * 2.54,
        ("cm", "in"): lambda v: v / 2.54,
        ("kg", "lbs"): lambda v: v * 2.20462,
        ("lbs", "kg"): lambda v: v / 2.20462,
        ("g", "oz"): lambda v: v * 0.035274,
        ("oz", "g"): lambda v: v / 0.035274,
        ("celsius", "fahrenheit"): lambda v: (v * 9.0 / 5.0) + 32.0,
        ("fahrenheit", "celsius"): lambda v: (v - 32.0) * 5.0 / 9.0,
        ("celsius", "kelvin"): lambda v: v + 273.15,
        ("kelvin", "celsius"): lambda v: v - 273.15,
    }

    key = (from_unit.lower().strip(), to_unit.lower().strip())
    if key in conversions:
        result = conversions[key](value)
        rounded = round(result, 4)
        return {
            "original_value": value,
            "from_unit": from_unit,
            "converted_value": rounded,
            "result_value": rounded,
            "to_unit": to_unit,
        }
    return {
        "error": f"Unsupported unit conversion from '{from_unit}' to '{to_unit}'."
    }


def basic_calculator(
    operation: str,
    a: float,
    b: float,
) -> Dict[str, Any]:
    """Performs a basic arithmetic calculation between two numbers."""
    op = operation.lower().strip()
    if op in ("add", "+", "plus"):
        res = a + b
    elif op in ("subtract", "-", "minus"):
        res = a - b
    elif op in ("multiply", "*", "times"):
        res = a * b
    elif op in ("divide", "/", "div"):
        if b == 0:
            return {"error": "Division by zero is undefined."}
        res = a / b
    elif op in ("power", "^", "pow"):
        res = a**b
    else:
        return {"error": f"Unsupported operation: {operation}"}

    return {"operation": operation, "a": a, "b": b, "result": res}
