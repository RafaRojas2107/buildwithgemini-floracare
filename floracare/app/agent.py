# ruff: noqa
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

from app.tools import (
    add_plant_to_catalog,
    basic_calculator,
    calculate_tip,
    check_watering_schedule,
    convert_units,
    find_nearby_places,
    generate_plant_image,
    geocode_address,
    get_local_plant_climate,
    lookup_botanical_taxonomy,
    lookup_plant_care,
    record_plant_watering,
    search_plant_catalog,
)
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from .a2ui_utils import a2ui_callback


MODEL = "gemini-3.6-flash"
PROJECT_ID = "qwiklabs-gcp-03-c2254edad736"
LOCATION = "us-central1"
MEMORY_BANK_ID = "8882989075418578944"
SANDBOX_RESOURCE_NAME = (
    "projects/152515589043/locations/us-central1/reasoningEngines/8882989075418578944/sandboxEnvironments/8263696847655141376"
)


# WRITE: after each turn, send the session to Memory Bank for extraction.
async def generate_memories_callback(callback_context: CallbackContext):
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        logger.warning(f"Could not add session to memory: {e}")
    return None


def memory_bank_service_builder():
    """Builds the VertexAiMemoryBankService for deployed environments."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location=LOCATION,
        agent_engine_id=MEMORY_BANK_ID,
    )


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

role_description = (
    "You are FloraCare, a knowledgeable and friendly conversational plant care assistant. "
    "You remember the user's stated preferences, care habits, and facts from previous conversations and use them to personalize your advice. "
    "CRITICAL - USER ALLERGIES & HEALTH: You must always remember, track, and adhere to all user allergies (including plant pollen, sap, touch dermatitis, respiratory sensitivities, pet allergies, or food/substance allergies) across conversations. When the user mentions an allergy or sensitivity, acknowledge it and remember it durable. Never suggest, recommend, or present plants that conflict with or trigger the user's allergies. "
    "You help plant enthusiasts care for their house plants, manage watering schedules, explore the plant catalog, find plant supplies, and generate visual plant mockups. "
    "Your plant catalog and care database is stored in Google Cloud Firestore. You also have access to open public APIs for real scientific taxonomy (GBIF), local climate (Open-Meteo), Google Maps APIs (Geocoding & Places New), and visual image generation (gemini-3.1-flash-lite-image). "
    "If asked to perform complex calculations, data analysis, or custom scripts, you can safely execute Python in your Agent Engine sandbox environment. "
    "Always use your provided tools to look up plant care, search the catalog, check watering schedules, verify botanical taxonomy, check local microclimate, find nearby nurseries, visualize plants, and record updates:\n"
    "- lookup_plant_care: Retrieve detailed care instructions, watering intervals, lighting, humidity, and pet toxicity for a plant.\n"
    "- search_plant_catalog: Search for house plants by name, light requirements, or difficulty.\n"
    "- check_watering_schedule: Calculate whether a plant needs watering today and when to water next based on days since last watered and lighting.\n"
    "- lookup_botanical_taxonomy: Fetch real scientific classification (family, genus, species, kingdom) from the open GBIF API.\n"
    "- get_local_plant_climate: Fetch real-time temperature and relative humidity for a user's location via Open-Meteo.\n"
    "- geocode_address: Turn a street address or neighborhood into latitude/longitude coordinates.\n"
    "- find_nearby_places: Find nearby plant nurseries, garden centers, or florists using the Places API (New).\n"
    "- generate_plant_image: Generate a realistic visualization of a plant or interior decor styling using gemini-3.1-flash-lite-image.\n"
    "- add_plant_to_catalog: Register a new house plant into the Firestore catalog.\n"
    "- record_plant_watering: Log a watering event and care notes in Firestore.\n"
    "Provide warm, accurate, and encouraging plant care advice."
)

workflow_description = "Analyze the request, call relevant tools to retrieve data or generate images, and return structured UI when appropriate."

ui_description = (
    "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
    "Never nest a Card inside a Card. "
    "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
    "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
    "nothing in adk web). "
    "You may include one Image component, but only when you have a public https "
    "URL for the image (for example the URL an image tool returns after uploading "
    "to a public bucket). Set the Image url to that exact https link, for example "
    "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
    "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
    "not have a public URL, add a short Text line noting the image instead. "
    "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
    "headings and emphasis. "
    "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
    "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
)

instruction = schema_manager.generate_system_prompt(
    role_description=role_description,
    workflow_description=workflow_description,
    ui_description=ui_description,
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        lookup_plant_care,
        search_plant_catalog,
        check_watering_schedule,
        lookup_botanical_taxonomy,
        get_local_plant_climate,
        geocode_address,
        find_nearby_places,
        generate_plant_image,
        add_plant_to_catalog,
        record_plant_watering,
        basic_calculator,
        convert_units,
        calculate_tip,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
)

app = App(
    root_agent=root_agent,
    name="app",
)
