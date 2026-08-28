"""Export the OpenAPI spec to a JSON file for frontend codegen."""

import json
import sys

sys.path.insert(0, ".")
from src.main import app

spec = app.openapi()
with open("openapi.json", "w") as f:
    json.dump(spec, f, indent=2)
print(f"Exported OpenAPI spec: {len(spec.get('paths', {}))} paths")
