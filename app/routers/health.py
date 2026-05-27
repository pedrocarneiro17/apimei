from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
