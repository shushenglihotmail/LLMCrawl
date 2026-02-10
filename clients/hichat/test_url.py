import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv(".env")
import base64
import hashlib
import secrets

import requests
from claude_auth import AUTH_URL, ClaudeAuthClient, find_available_port

client = ClaudeAuthClient()
port = find_available_port()
redirect_uri = f"http://localhost:{port}/callback"

code_verifier = secrets.token_urlsafe(64)
code_challenge = (
    base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
    .decode("utf-8")
    .rstrip("=")
)
state = secrets.token_urlsafe(16)

params = {
    "code": "true",
    "client_id": client.client_id,
    "response_type": "code",
    "redirect_uri": redirect_uri,
    "scope": client.scopes,
    "code_challenge": code_challenge,
    "code_challenge_method": "S256",
    "state": state,
}

url = requests.Request("GET", AUTH_URL, params=params).prepare().url
print("OUR URL:")
print(url)
print()
print("OFFICIAL CLI URL (for comparison):")
print(
    "https://platform.claude.com/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A62037%2Fcallback&scope=org%3Acreate_api_key+user%3Aprofile+user%3Ainference+user%3Asessions%3Aclaude_code&code_challenge=GsulFO9VGOoMvV5pIM3Lr0f_4bAD49RN2W18fQpkQnI&code_challenge_method=S256&state=qxN1gJRZajikEpMpNaayKsCigt_oafHO7xArVJLy-EA"
)
