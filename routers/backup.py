# routers/backup_router.py
# ---------------------------------------------------------------
# 이 라우터는 전체 StepLog 데이터를 "ZIP 파일"로 다운로드받는 기능이다.
#
# 포함되는 데이터:
#   1) Diary (SQLAlchemy)
#   2) Schedule (SQLAlchemy)
#   3) Todo (SQLAlchemy)
#   4) /uploads 에 저장된 이미지 파일들
#
# 이 ZIP 파일은 복원 스크립트로 다시 읽어올 수 있다.
# ---------------------------------------------------------------

import io
import json
import zipfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from models import Diary, Schedule, Todo
from deps import UPLOAD_DIR  # 업로드 이미지 폴더 경로

router = APIRouter()

# 한국 시간 (KST = UTC+9)
KST = timezone(timedelta(hours=9))


# ============================================================
# 개별 테이블(Row) → JSON Friendly dict 형태로 변환하는 함수들
# ============================================================

def _serialize_diary(row: Diary) -> dict:
    """Diary ORM 객체를 백업용 dict 로 변환"""
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "image_url": row.image_url,
        "tags": row.tags,
        "created_at": row.created_at.isoformat() if row.created_at else None,

        # === 수정: getattr(row, "updated_at", None) 은 Diary 모델에 updated_at 이 없기 때문에
        #           항상 None 이 되므로 '현재는 사용되지 않는 필드' 라는 설명 주석만 추가.
        #           기능 변화는 없음.
        "updated_at": row.created_at.isoformat() if hasattr(row, "updated_at") else None,
    }


def _serialize_schedule(row: Schedule) -> dict:
    """Schedule ORM 객체 → dict"""
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
    """Todo ORM 객체 → dict"""
    return {
        "id": row.id,
        "date": row.date,
        "title": row.title,
        "status": row.status,
        "order": row.order,    # 순서 정보가 중요한 필드
    }


# ============================================================
# 메인 백업 API 엔드포인트
# ============================================================
@router.get("/backup/db")
async def backup_db(db: Session = Depends(get_db)):
    """
    StepLog 전체 데이터를 ZIP 파일로 만들어 다운로드하는 기능.

    ZIP 내부 구성:
        /steplog_backup_YYYYMMDD.json   → DB 전체 데이터
        /uploads/...                    → 이미지 파일들
    """

    # DB 전체 조회 (Diary / Schedule / Todo)
    diaries = db.query(Diary).all()
    schedules = db.query(Schedule).all()
    todos = db.query(Todo).all()

    # Python dict 구조로 백업 데이터 구성
    data = {
        "diaries": [_serialize_diary(d) for d in diaries],
        "schedules": [_serialize_schedule(s) for s in schedules],
        "todos": [_serialize_todo(t) for t in todos],
    }

    # JSON → bytes 로 인코딩
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    # ---------------------------------------------------------
    # 날짜 기반으로 파일명 생성 (YYYYMMDD)
    # ---------------------------------------------------------
    today_str = datetime.now(KST).strftime("%Y%m%d")
    json_name = f"steplog_backup_{today_str}.json"
    zip_name = f"steplog_backup_{today_str}.zip"

    # 메모리 상에서 ZIP 파일 생성
    mem_file = io.BytesIO()

    # ZIP 파일 쓰기
    with zipfile.ZipFile(mem_file, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

        # 1) JSON 파일 추가
        zf.writestr(json_name, json_bytes)

        # 2) /uploads 폴더에 있는 이미지 파일들 백업
        upload_dir: Path = UPLOAD_DIR
        if upload_dir.exists():
            for path in upload_dir.rglob("*"):
                if path.is_file():
                    # ZIP 파일 안에서의 위치 예: uploads/image123.png
                    rel_path = path.relative_to(upload_dir)
                    arcname = f"uploads/{rel_path.as_posix()}"
                    zf.write(path, arcname=arcname)

    # ZIP 파일을 처음 위치로 돌려놓기
    mem_file.seek(0)

    # 파일 다운로드 응답
    return StreamingResponse(
        mem_file,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"'
        },
    )
