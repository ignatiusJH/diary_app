# routers/restore_router.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from deps import DATA_DIR, owner_only
import shutil

router = APIRouter()


@router.post("/restore/db")
async def restore_db(file: UploadFile = File(...), auth=owner_only):
    """
    업로드한 SQLite DB 파일을 서버의 steplog.db로 교체
    """
    if not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="DB 파일(.db)이 아닙니다.")

    target_path = DATA_DIR / "steplog.db"

    try:
        with target_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        raise HTTPException(status_code=500, detail="DB 복원 실패")

    return RedirectResponse(url="/stats?restored=1", status_code=303)
