# routers/restore_router.py
from pathlib import Path
import shutil
import zipfile

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import RedirectResponse

from deps import DATA_DIR, UPLOAD_DIR, DB_PATH, owner_only

router = APIRouter()


@router.post("/restore/db", dependencies=[Depends(owner_only)])
async def restore_db(file: UploadFile = File(...)):
    """
    steplog.db 또는 ZIP(steplog.db + uploads/)를 업로드 받아서 복원한다.

    - .db  파일  → DB만 교체
    - .zip 파일  → 내부의 steplog.db + uploads/ 전체 복원
    """
    filename = (file.filename or "").lower()

    # 업로드 파일을 임시로 저장
    tmp_path = DATA_DIR / "_restore_upload_tmp"
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        # 1) .db 만 복원하는 경우 (옛 백업 호환)
        if filename.endswith(".db"):
            shutil.move(tmp_path, DB_PATH)

        # 2) .zip 을 통한 DB + 이미지 통합 복원
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(tmp_path, "r") as zf:
                members = zf.namelist()

                # 2-1) steplog.db 찾기
                db_member = None
                for name in members:
                    if name.endswith("steplog.db"):
                        db_member = name
                        break

                if db_member is None:
                    raise HTTPException(status_code=400, detail="ZIP 안에 steplog.db가 없습니다.")

                # steplog.db 추출 후 위치로 이동
                zf.extract(db_member, DATA_DIR)
                extracted_db = DATA_DIR / db_member
                extracted_db.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(extracted_db, DB_PATH)

                # 2-2) uploads/ 이하 파일들 복원
                for name in members:
                    # 디렉토리는 건너뛰기
                    if not name.startswith("uploads/") or name.endswith("/"):
                        continue

                    zf.extract(name, DATA_DIR)
                    src = DATA_DIR / name
                    rel = Path(name).relative_to("uploads")
                    dest = UPLOAD_DIR / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(src, dest)

        else:
            raise HTTPException(
                status_code=400,
                detail="지원하지 않는 파일 형식입니다. .db 또는 .zip만 업로드하세요.",
            )

    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return RedirectResponse(url="/stats?restored=1", status_code=303)
