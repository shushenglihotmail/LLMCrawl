import json
import sys

data = json.load(sys.stdin)
print(f'Cookies in container: {len(data["cookies"])}')
for i, cookie in enumerate(data["cookies"], 1):
    print(f'{i}. {cookie.get("name", "unnamed")} - {cookie.get("domain", "no domain")}')
