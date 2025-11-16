#!/usr/bin/env python3
"""Test if authentication credentials work for www.osgwiki.com"""

import json
from pathlib import Path

import requests


def test_auth():
    # Load the auth file
    auth_file = Path(".auth/www_osgwiki_com.json")
    if not auth_file.exists():
        print(f"Error: Auth file not found: {auth_file}")
        return False

    with open(auth_file) as f:
        auth_data = json.load(f)

    # Extract cookies
    cookies = {}
    for cookie in auth_data["storage_state"]["cookies"]:
        if cookie["domain"] in ["www.osgwiki.com", ".osgwiki.com"]:
            cookies[cookie["name"]] = cookie["value"]

    print(f"Testing with {len(cookies)} cookies from www.osgwiki.com:")
    for name in cookies.keys():
        print(f"  - {name}")

    # Test request
    url = "https://www.osgwiki.com/wiki/Main_Page"
    print(f"\nTesting: {url}")

    try:
        response = requests.get(
            url,
            cookies=cookies,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=10,
            allow_redirects=True,
        )

        print(f"\nStatus Code: {response.status_code}")
        print(f"Final URL: {response.url}")

        if response.status_code == 200:
            # Check if we're actually logged in
            content = response.text.lower()
            if "sign in" in content or "login" in content:
                print("\n❌ Got 200 but seems to require login")
                return False
            else:
                print("\n✅ Authentication successful!")
                print(f"Content length: {len(response.text)} bytes")

                # Show a snippet
                if "mediawiki" in content or "wiki" in content:
                    print("✅ Page appears to be MediaWiki content")

                return True
        elif response.status_code == 401:
            print("\n❌ Authentication failed (401 Unauthorized)")
            return False
        elif response.status_code == 403:
            print("\n❌ Access forbidden (403)")
            return False
        else:
            print(f"\n⚠ Unexpected status: {response.status_code}")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_auth()
    exit(0 if success else 1)
