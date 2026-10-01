"""Seed script to populate Firestore with initial plant care data."""

import datetime
from google.cloud import firestore

# Explicitly pin project ID as string per Agent Platform requirements
PROJECT_ID = "qwiklabs-gcp-03-c2254edad736"
COLLECTION_NAME = "plants"

INITIAL_PLANTS = [
    {
        "id": "monstera-deliciosa",
        "name": "Monstera Deliciosa",
        "scientific_name": "Monstera deliciosa",
        "watering_frequency_days": 7,
        "watering_instructions": (
            "Water when the top 2-3 inches of soil feel dry to the touch. "
            "In medium indirect light, water every 7-10 days. Ensure good pot drainage."
        ),
        "light_requirement": "medium to bright indirect light",
        "care_difficulty": "moderate",
        "humidity": "moderate to high (50-60%)",
        "toxicity": "Toxic to cats and dogs if ingested (calcium oxalate crystals)",
        "last_watered_date": None,
        "care_notes": "Iconic split leaves (fenestrations). Wipe dust off leaves periodically.",
    },
    {
        "id": "snake-plant",
        "name": "Snake Plant",
        "scientific_name": "Dracaena trifasciata",
        "watering_frequency_days": 14,
        "watering_instructions": (
            "Allow soil to dry out completely between waterings. "
            "Water every 2-3 weeks in average conditions; even less in winter."
        ),
        "light_requirement": "low to bright indirect light",
        "care_difficulty": "easy",
        "humidity": "tolerant of low humidity (30-40%)",
        "toxicity": "Mildly toxic to pets if chewed",
        "last_watered_date": None,
        "care_notes": "Extremely hardy, drought tolerant, excellent air-purifying plant.",
    },
    {
        "id": "golden-pothos",
        "name": "Golden Pothos",
        "scientific_name": "Epipremnum aureum",
        "watering_frequency_days": 7,
        "watering_instructions": (
            "Water when the top 1-2 inches of soil feel dry. Drooping leaves indicate it is thirsty."
        ),
        "light_requirement": "low to bright indirect light",
        "care_difficulty": "easy",
        "humidity": "adaptable, prefers 40-60%",
        "toxicity": "Toxic to cats and dogs if ingested",
        "last_watered_date": None,
        "care_notes": "Fast-growing trailing vine. Easily propagated in water.",
    },
    {
        "id": "fiddle-leaf-fig",
        "name": "Fiddle Leaf Fig",
        "scientific_name": "Ficus lyrata",
        "watering_frequency_days": 8,
        "watering_instructions": (
            "Water when the top 2 inches of soil are dry. Sensitive to overwatering and dry spells."
        ),
        "light_requirement": "bright indirect light",
        "care_difficulty": "moderate",
        "humidity": "high humidity (50-65%)",
        "toxicity": "Toxic to pets",
        "last_watered_date": None,
        "care_notes": "Prefers consistent location away from cold drafts. Rotate weekly for even growth.",
    },
    {
        "id": "peace-lily",
        "name": "Peace Lily",
        "scientific_name": "Spathiphyllum",
        "watering_frequency_days": 6,
        "watering_instructions": (
            "Keep soil consistently lightly moist, but not soggy. Leaves will droop dramatically when dry."
        ),
        "light_requirement": "medium to low indirect light",
        "care_difficulty": "easy",
        "humidity": "high humidity (50-60%)",
        "toxicity": "Toxic to dogs and cats",
        "last_watered_date": None,
        "care_notes": "Produces elegant white blooms. Tolerates lower light conditions well.",
    },
    {
        "id": "zz-plant",
        "name": "ZZ Plant",
        "scientific_name": "Zamioculcas zamiifolia",
        "watering_frequency_days": 18,
        "watering_instructions": (
            "Water thoroughly only when soil is completely dry throughout the pot. Rhizomes store water."
        ),
        "light_requirement": "low to bright indirect light",
        "care_difficulty": "easy",
        "humidity": "tolerant of dry air (30-50%)",
        "toxicity": "Toxic if ingested",
        "last_watered_date": None,
        "care_notes": "Glossy green foliage, nearly indestructible, thrives on neglect.",
    },
]


def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    print(f"Seeding {len(INITIAL_PLANTS)} plants into '{COLLECTION_NAME}' collection...")
    for plant in INITIAL_PLANTS:
        doc_id = plant["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(plant)
        print(f"  ✓ Seeded: {plant['name']} (ID: {doc_id})")

    print(f"Successfully seeded {len(INITIAL_PLANTS)} plants into Firestore!")


if __name__ == "__main__":
    seed_database()
