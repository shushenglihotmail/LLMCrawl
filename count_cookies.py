import json

with open(r"C:\src\github\LLMCrawl\deploy\.env", "r", encoding="utf-8") as f:
    content = f.read()

line = content.split("FIRECRAWL_AUTH_STORAGE_STATE=")[1].strip()
data = json.loads(line)
print(f'Total cookies: {len(data["cookies"])}')

for i, cookie in enumerate(data["cookies"], 1):
    print(f'{i}. {cookie.get("name", "unnamed")} - {cookie.get("domain", "no domain")}')
