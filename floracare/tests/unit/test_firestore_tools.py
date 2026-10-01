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

"""Unit tests for FloraCare Firestore tools."""

import pytest
from app.tools import (
    FIRESTORE_PROJECT,
    IMAGE_BUCKET_NAME,
    add_plant_to_catalog,
    check_watering_schedule,
    find_nearby_places,
    generate_plant_image,
    geocode_address,
    get_local_plant_climate,
    lookup_botanical_taxonomy,
    lookup_plant_care,
    record_plant_watering,
    search_plant_catalog,
)


def test_firestore_project_id_is_string():
    """Verify project ID is pinned as a non-empty string."""
    assert isinstance(FIRESTORE_PROJECT, str)
    assert FIRESTORE_PROJECT == "qwiklabs-gcp-03-c2254edad736"


def test_search_plant_catalog():
    """Verify searching the Firestore plant catalog."""
    # Search all
    all_plants = search_plant_catalog()
    assert len(all_plants) >= 6

    # Search by keyword
    monstera_results = search_plant_catalog(query="Monstera")
    assert len(monstera_results) >= 1
    assert any("Monstera" in p["name"] for p in monstera_results)

    # Search by difficulty
    easy_plants = search_plant_catalog(care_difficulty="easy")
    assert len(easy_plants) >= 3
    assert all(p["care_difficulty"] == "easy" for p in easy_plants)


def test_lookup_plant_care():
    """Verify looking up care details for Monstera Deliciosa."""
    plant = lookup_plant_care("Monstera Deliciosa")
    assert "error" not in plant
    assert plant["name"] == "Monstera Deliciosa"
    assert plant["scientific_name"] == "Monstera deliciosa"
    assert plant["watering_frequency_days"] == 7
    assert "medium to bright indirect light" in plant["light_requirement"]
    assert "Toxic" in plant["toxicity"]


def test_check_watering_schedule():
    """Verify watering schedule calculation (5 days ago, medium light)."""
    schedule = check_watering_schedule(
        plant_name="Monstera Deliciosa",
        days_since_last_watered=5,
        light_level="medium",
    )
    assert "error" not in schedule
    assert schedule["plant_name"] == "Monstera Deliciosa"
    assert schedule["days_since_last_watered"] == 5
    assert schedule["base_interval_days"] == 7
    # 7 - 5 = 2 days remaining
    assert schedule["days_until_next_watering"] == 2
    assert schedule["needs_watering_now"] is False


def test_check_watering_schedule_due():
    """Verify watering schedule calculation when plant is overdue for water."""
    schedule = check_watering_schedule(
        plant_name="Monstera Deliciosa",
        days_since_last_watered=10,
        light_level="medium",
    )
    assert schedule["needs_watering_now"] is True
    assert schedule["days_until_next_watering"] == 0


def test_add_and_update_plant_in_catalog():
    """Verify writing a new plant to Firestore and updating watering record."""
    plant_name = "Spider Plant Test"
    result = add_plant_to_catalog(
        name=plant_name,
        scientific_name="Chlorophytum comosum",
        watering_frequency_days=7,
        light_requirement="bright indirect light",
        care_difficulty="easy",
        watering_instructions="Water when top half of soil is dry.",
        care_notes="Produces baby spiderettes.",
    )
    assert result["status"] == "success"

    # Verify lookup succeeds
    looked_up = lookup_plant_care(plant_name)
    assert looked_up["name"] == plant_name

    # Record watering
    water_result = record_plant_watering(
        plant_name=plant_name,
        watering_date="2026-10-01",
        notes="Watered with filtered water.",
    )
    assert water_result["status"] == "success"
    assert water_result["last_watered_date"] == "2026-10-01"


def test_lookup_botanical_taxonomy():
    """Verify botanical taxonomy lookup via the public GBIF API."""
    result = lookup_botanical_taxonomy("Monstera deliciosa")
    assert result.get("found") is True
    assert result.get("family") == "Araceae"
    assert result.get("genus") == "Monstera"
    assert result.get("species") == "Monstera deliciosa"
    assert result.get("rank") == "SPECIES"


def test_lookup_botanical_taxonomy_not_found():
    """Verify behavior when plant name has no match."""
    result = lookup_botanical_taxonomy("nonexistentplantxyz123456")
    assert result.get("found") is False


def test_get_local_plant_climate():
    """Verify weather and humidity fetching via the public Open-Meteo API."""
    result = get_local_plant_climate("Austin")
    assert "error" not in result
    assert "Austin" in result["location"]
    assert "temperature_celsius" in result
    assert "relative_humidity_percentage" in result
    assert "climate_advisory" in result
    assert isinstance(result["relative_humidity_percentage"], (int, float))


def test_geocode_address_placeholder_key():
    """Verify geocode_address detects unconfigured/placeholder API key."""
    result = geocode_address("1600 Amphitheatre Pkwy, Mountain View, CA")
    assert "error" in result
    assert "GOOGLE_MAPS_API_KEY" in result["error"]


def test_find_nearby_places_placeholder_key():
    """Verify find_nearby_places detects unconfigured/placeholder API key."""
    result = find_nearby_places(37.422, -122.084, place_type="florist")
    assert "error" in result
    assert "GOOGLE_MAPS_API_KEY" in result["error"]


def test_geocode_address_mocked(monkeypatch):
    """Verify geocoding response parsing for address and location."""
    import io
    import json
    import urllib.request

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "dummy_valid_key")

    mock_resp_data = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
                "geometry": {
                    "location": {"lat": 37.4224764, "lng": -122.0842499}
                },
                "place_id": "ChIJ2eUgeAK6j4ARbn5u_wAGqWA",
            }
        ],
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(mock_resp_data).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: MockResponse())

    result = geocode_address("1600 Amphitheatre Pkwy, Mountain View, CA")
    assert "error" not in result
    assert result["address"] == "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA"
    assert result["location"]["latitude"] == 37.4224764
    assert result["location"]["longitude"] == -122.0842499


def test_find_nearby_places_mocked(monkeypatch):
    """Verify Places (New) nearby search response parsing for name, address, and location."""
    import io
    import json
    import urllib.request

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "dummy_valid_key")

    mock_resp_data = {
        "places": [
            {
                "displayName": {"text": "Green Thumb Plant Nursery", "languageCode": "en"},
                "formattedAddress": "123 Garden Way, Austin, TX 78701",
                "location": {"latitude": 30.27, "longitude": -97.74},
            }
        ]
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(mock_resp_data).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: MockResponse())

    result = find_nearby_places(latitude=30.27, longitude=-97.74, place_type="florist")
    assert "error" not in result
    assert result["total_found"] == 1
    place = result["places"][0]
    assert place["name"] == "Green Thumb Plant Nursery"
    assert place["address"] == "123 Garden Way, Austin, TX 78701"
    assert place["location"]["latitude"] == 30.27
    assert place["location"]["longitude"] == -97.74


def test_image_bucket_name_is_hardcoded_string():
    """Verify bucket name is pinned as a string per Agent Platform requirements."""
    assert isinstance(IMAGE_BUCKET_NAME, str)
    assert IMAGE_BUCKET_NAME == "floracare-images-fbb32859"


@pytest.mark.asyncio
async def test_generate_plant_image_with_tool_context(monkeypatch):
    """Verify generate_plant_image saves artifact and uploads to GCS without writing local files."""
    from google import genai
    from google.cloud import storage

    # Mock GenAI response
    fake_image_bytes = b"fake-jpeg-image-bytes"

    class FakeInlineData:
        data = fake_image_bytes
        mime_type = "image/jpeg"

    class FakePart:
        inline_data = FakeInlineData()
        text = None

    class FakeContent:
        parts = [FakePart()]

    class FakeCandidate:
        content = FakeContent()

    class FakeResponse:
        candidates = [FakeCandidate()]

    class FakeModels:
        def generate_content(self, model, contents, config):
            assert model == "gemini-3.1-flash-lite-image"
            return FakeResponse()

    class FakeGenAIClient:
        models = FakeModels()

    monkeypatch.setattr(genai, "Client", lambda **kwargs: FakeGenAIClient())

    # Mock Storage Client
    uploaded_blobs = {}

    class FakeBlob:
        def __init__(self, name):
            self.name = name

        def upload_from_string(self, data, content_type):
            uploaded_blobs[self.name] = (data, content_type)

    class FakeBucket:
        def blob(self, name):
            return FakeBlob(name)

    class FakeStorageClient:
        def __init__(self, project):
            assert project == FIRESTORE_PROJECT

        def bucket(self, name):
            assert name == IMAGE_BUCKET_NAME
            return FakeBucket()

    monkeypatch.setattr(storage, "Client", FakeStorageClient)

    # Mock ToolContext
    saved_artifacts = {}

    class FakeToolContext:
        async def save_artifact(self, filename, artifact, custom_metadata=None):
            saved_artifacts[filename] = artifact
            return 1

    fake_ctx = FakeToolContext()

    result = await generate_plant_image(
        plant_name="Monstera Deliciosa",
        visual_description="in a ceramic white pot",
        tool_context=fake_ctx,
    )

    assert result["status"] == "success"
    assert result["plant_name"] == "Monstera Deliciosa"
    assert result["artifact_saved"] is True
    assert result["artifact_filename"] == "monstera-deliciosa.jpg"
    assert "monstera-deliciosa.jpg" in saved_artifacts
    assert result["public_url"].startswith("https://storage.googleapis.com/floracare-images-fbb32859/plants/monstera-deliciosa_")
    assert len(uploaded_blobs) == 1
    blob_key = list(uploaded_blobs.keys())[0]
    assert uploaded_blobs[blob_key] == (fake_image_bytes, "image/jpeg")




