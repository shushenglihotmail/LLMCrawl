"""Entry point for running memory service directly."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "services.memory_service.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8007")),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
