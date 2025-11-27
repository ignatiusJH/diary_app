# routers/backup.py
from datetime import datetime
import os
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from deps import DB_PATH, UPLOAD_DIR, DATA_DIR, owner_only

# 이 router는 /backup/db 하나만 담당
router = APIRouter(
    tags=["backup"],
)


@router.get("/backup/db", dependencies=[Depends(owner_only)])
async def download_db():
    """
    steplog.db + uploads 폴더를 ZIP으로 묶어서 내려주는 백업 엔드포인트.

    - ZIP 파일 이름 예시:
      steplog_backup_20251127_0215.zip

    - ZIP 안 구조:
      steplog.db
      uploads/....(이미지 파일들)
    """
    db_path = DB_PATH

    if not db_path.exists():
        raise HTTPException(status_code=404, detail="DB 파일을 찾을 수 없습니다.")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    zip_name = f"steplog_backup_{ts}.zip"
    zip_path = DATA_DIR / zip_name

    # ZIP 생성
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) DB 파일
        zf.write(db_path, arcname="steplog.db")

        # 2) uploads 폴더 전체
        if UPLOAD_DIR.exists():
            for root, dirs, files in os.walk(UPLOAD_DIR):
                for fname in files:
                    full_path = Path(root) / fname
                    # ZIP 안에서는 uploads/ 하위 구조로 들어가게
                    rel_path = full_path.relative_to(UPLOAD_DIR)
                    arcname = Path("uploads") / rel_path
                    zf.write(full_path, arcname=str(arcname))

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_name,
    )
