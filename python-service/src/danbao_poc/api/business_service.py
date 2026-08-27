from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(title="Danbao Business Placeholder", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "deprecated", "service": "business-service", "message": "Use parse-service and retrieve-service directly."}

