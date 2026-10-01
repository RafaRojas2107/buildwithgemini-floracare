# My agent: FloraCare
One-liner: A conversational agent that helps plant enthusiasts care for their house plants and discover new varieties with a catalog of house plants, watering schedules, and diagnostic guides.

Tool coverage:
- Memory: Remembers user's house plant collection, watering/fertilizing history, home lighting conditions, and experience level.
- Tools: Look up plant care requirements (`lookup_plant_care`), check/calculate watering schedules (`check_watering_schedule`), and search plant catalog (`search_plant_catalog`).
- Catalog/UI: House plant catalog and personalized plant collection rendered as A2UI cards (care difficulty, light/water badges, plant images).
- Image gen: Generate visuals of mature plants or room decor previews with specific plant arrangements.
- Sandbox: Compute custom fertilizer dilution ratios and soil volume requirements based on pot dimensions.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): A2UI plant cards, AI plant image preview, soil/fertilizer volume calculator
First eval question: When should I water my Monstera Deliciosa if I last watered it 5 days ago and it receives medium indirect light?
