"""Test keyword search with the queries that VS Code AI agent sent."""

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from azure_devops_mcp_server.azure_client import AzureDevOpsClient

# Load .env from parent directory
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


async def test_query(client, description, **kwargs):
    """Test a single query and measure time."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Parameters: {kwargs}")
    print(f"{'='*60}")

    start_time = time.time()
    try:
        results = await client.search_files(**kwargs)
        elapsed = time.time() - start_time

        print(f"✅ SUCCESS in {elapsed:.2f} seconds")
        print(f"Found {len(results)} results")
        if results:
            print("\nFirst 3 results:")
            for i, result in enumerate(results[:3], 1):
                print(f"  {i}. {result['path']}")
        return True, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ FAILED after {elapsed:.2f} seconds")
        print(f"Error: {e}")
        return False, elapsed


async def main():
    """Run all tests."""
    # Get PAT from environment
    pat = os.environ.get("AZURE_DEVOPS_PAT")
    if not pat:
        print("ERROR: AZURE_DEVOPS_PAT environment variable not set")
        sys.exit(1)

    # Create client
    client = AzureDevOpsClient(
        organization="microsoft",
        project="OS",
        repository="os.2020",
        pat=pat,
        branch="official/rs_sparc_ctr_exp",
        max_results=50,
    )

    # Authenticate
    print("Authenticating...")
    if not await client.authenticate(use_interactive=False):
        print("Authentication failed!")
        sys.exit(1)
    print("✅ Authenticated\n")

    # Test queries from VS Code AI agent
    queries = [
        {
            "description": "Query 1: extension=json + keyword search + recursive",
            "extension": "json",
            "keyword": "Microsoft-Windows-Runtime-Metadata-NanoServer",
            "recursive": True,
            "max_results": 10,
        },
        {
            "description": "Query 2: keyword only + recursive",
            "keyword": "Microsoft-NanoServer-Licensing",
            "recursive": True,
            "max_results": 10,
        },
        {
            "description": "Query 3: file_pattern + recursive",
            "file_pattern": "Microsoft-Windows-Runtime-Metadata-NanoServer.*",
            "recursive": True,
            "max_results": 10,
        },
    ]

    results = []
    for query in queries:
        desc = query.pop("description")
        success, elapsed = await test_query(client, desc, **query)
        results.append((desc, success, elapsed))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for desc, success, elapsed in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} ({elapsed:.2f}s): {desc}")

    # Check if any timeouts (> 120 seconds)
    slow_queries = [(d, e) for d, s, e in results if e > 120]
    if slow_queries:
        print(f"\n⚠️  WARNING: {len(slow_queries)} queries took > 120 seconds:")
        for desc, elapsed in slow_queries:
            print(f"  - {desc}: {elapsed:.2f}s")
    else:
        print(f"\n✅ All queries completed within timeout limit!")


if __name__ == "__main__":
    asyncio.run(main())
