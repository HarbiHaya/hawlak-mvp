from fastapi import APIRouter, HTTPException

from app.services.object_storage import ObjectStorageError, StorageDep

router = APIRouter()


@router.get("/health/storage")
def storage_health(storage: StorageDep) -> dict[str, str]:
    try:
        storage.ensure_bucket()
    except ObjectStorageError as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    return {"status": "ok", "bucket": storage.bucket}
