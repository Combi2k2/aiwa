"""Try the openjev decision API with the example from its docs."""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

response = requests.post(
    "https://api.openjev.sh/v1/systemone",
    headers={"Authorization": f"Bearer {os.environ['OPENJEV_API_KEY']}"},
    json={
        "model": "openjev",
        "state": "My card was charged twice. Please help ASAP.",
        "questions": {
            "urgent": {
                "type": "noul",
                "instructions": "Does this message convey urgency?",
                "criteria": {
                    "true": "Explicitly time-sensitive",
                    "false": "No urgency expressed",
                },
            },
            "team": {
                "type": "choice",
                "instructions": "Which team should handle this?",
                "criteria": {
                    "billing": "Payments and refunds",
                    "technical": "Bugs and integrations",
                    "sales": "Pricing and new accounts",
                },
            },
        },
    },
    timeout=60,
)
print("HTTP", response.status_code)
try:
    print(json.dumps(response.json(), indent=2))
except ValueError:
    print(response.text[:2000])
response.raise_for_status()
