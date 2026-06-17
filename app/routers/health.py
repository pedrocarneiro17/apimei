import os
import glob
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/debug/screenshots", summary="Lista screenshots de erro salvos")
def listar_screenshots():
    arquivos = sorted(glob.glob("/tmp/pgmei_*.png"), reverse=True)
    return {"screenshots": [os.path.basename(f) for f in arquivos]}


@router.get("/debug/screenshot/{nome}", summary="Retorna um screenshot de erro")
def ver_screenshot(nome: str):
    if "/" in nome or ".." in nome:
        raise HTTPException(status_code=400, detail="Nome inválido")
    path = f"/tmp/{nome}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Screenshot não encontrado")
    return FileResponse(path, media_type="image/png")
