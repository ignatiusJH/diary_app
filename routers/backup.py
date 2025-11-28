# routers/backup_router.py
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from models import Diary, Schedule, Todo
from deps import UPLOAD_DIR  # <- 이미지 폴더

router = APIRouter()


def _serialize_diary(row: Diary) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "image_url": row.image_url,
        "tags": row.tags,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
    }


def _serialize_schedule(row: Schedule) -> dict:
    return {
        "id": row.id,
        "date": row.date,
        "title": row.title,
        "memo": row.memo,
        "time_str": row.time_str,
        "place": row.place,
        "done": row.done,
    }


def _serialize_todo(row: Todo) -> dict:
    return {
        "id": row.id,
        "date": row.date,
        "title": row.title,
        "status": row.status,
        "order": row.order,
    }


@router.get("/backup/db")
async def backup_db(
    db: Session = Depends(get_db),
):
    """
    전체 DB(Diary, Schedule, Todo) + /uploads 이미지 파일들을
    하나의 ZIP(steplog_backup.zip)으로 내려준다.
    """
    diaries = db.query(Diary).all()
    schedules = db.query(Schedule).all()
    todos = db.query(Todo).all()

    data = {
        "diaries": [_serialize_diary(d) for d in diaries],
        "schedules": [_serialize_schedule(s) for s in schedules],
        "todos": [_serialize_todo(t) for t in todos],
    }

    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    mem_file = io.BytesIO()
    with zipfile.ZipFile(mem_file, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1) DB 백업 JSON
        zf.writestr("steplog_backup.json", json_bytes)

        # 2) 이미지 파일들 (/uploads/ 경로로 넣어주기)
        upload_dir: Path = UPLOAD_DIR

        if upload_dir.exists():
            for path in upload_dir.rglob("*"):
                if path.is_file():
                    # ZIP 안에서의 파일 이름: uploads/xxx.png
                    rel_path = path.relative_to(upload_dir)
                    arcname = f"uploads/{rel_path.as_posix()}"
                    zf.write(path, arcname=arcname)

    mem_file.seek(0)

    return StreamingResponse(
        mem_file,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="steplog_backup.zip"'
        },
    )
