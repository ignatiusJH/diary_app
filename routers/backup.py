# routers/backup.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from deps import DB_PATH, owner_only

# 이 router는 /backup/db 하나만 담당
router = APIRouter(
    tags=["backup"],
)


@router.get("/backup/db", dependencies=[Depends(owner_only)])
async def download_db():
    """
    steplog.db 파일을 그대로 다운로드해 주는 백업 엔드포인트.
    통계 화면 오른쪽 아래 버튼에서 이 URL을 호출한다.
    """
    db_path = DB_PATH

    if not db_path.exists():
        raise HTTPException(status_code=404, detail="DB 파일을 찾을 수 없습니다.")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"steplog_backup_{ts}.db"

    return FileResponse(
        path=str(db_path),
        media_type="application/octet-stream",
        filename=filename,
    )
