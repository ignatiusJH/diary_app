# routers/restore_router.py
# ---------------------------------------------------------
# 이 라우터는 ZIP 파일을 업로드해서
# 전체 DB(Diary, Schedule, Todo)와 /uploads 이미지 파일을
# 통째로 복원하는 기능을 담당한다.
#
# ⚠ 매우 위험한 기능이다.
#    기존 DB 내용을 모두 삭제하고, ZIP의 데이터로 완전히 갈아끼운다.
# ---------------------------------------------------------

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from db import get_db
from models import Diary, Schedule, Todo
from deps import UPLOAD_DIR  # 이미지 저장 폴더

router = APIRouter()


@router.post("/restore/db", response_class=RedirectResponse)
async def restore_db(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    업로드된 ZIP 파일에서
    - steplog_backup.json (구버전)
    - steplog_backup_YYYYMMDD.json (신버전)
    - uploads/ 폴더 내 이미지들
    을 읽어서 DB + 이미지 파일을 통째로 복원한다.

    ⚠ 기존 DB 내용 전부 삭제됨.
    ⚠ 기존 uploads 파일도 ZIP 내용으로 덮어쓰기됨.
    """

    # -----------------------------
    # 1) 확장자 검사
    # -----------------------------
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="ZIP 파일을 업로드해주세요.")

    # ZIP 파일 내용을 메모리로 읽기
    content = await file.read()

    try:
        mem_file = io.BytesIO(content)

        # -----------------------------
        # 2) ZIP 파일 열기
        # -----------------------------
        with zipfile.ZipFile(mem_file, mode="r") as zf:
            namelist = zf.namelist()

            # === 수정: 백업 JSON 파일 이름 호환 처리 ===
            # 1순위: 예전 이름 steplog_backup.json
            # 2순위: steplog_backup_YYYYMMDD.json 패턴 중 하나 (여러 개면 가장 최근 이름)
            backup_json_name: str | None = None

            # 1) 구버전 이름이 있으면 그걸 우선 사용
            if "steplog_backup.json" in namelist:
                backup_json_name = "steplog_backup.json"
            else:
                # 2) 새 버전 패턴: steplog_backup_YYYYMMDD.json
                candidates = [
                    name
                    for name in namelist
                    if name.startswith("steplog_backup_") and name.endswith(".json")
                ]
                if candidates:
                    # 여러 개 있으면 이름 기준으로 정렬해서 '가장 뒤에 것(보통 최신)' 사용
                    backup_json_name = sorted(candidates)[-1]

            if not backup_json_name:
                # 둘 중 어느 패턴도 없으면 에러
                raise HTTPException(
                    status_code=400,
                    detail="steplog_backup.json 또는 steplog_backup_YYYYMMDD.json 이 포함된 백업 ZIP이 아닙니다.",
                )
            # === 수정 끝 ===

            # JSON 데이터 읽기
            json_bytes = zf.read(backup_json_name)

            # uploads/... 이미지 목록
            image_names = [name for name in namelist if name.startswith("uploads/")]

            # -----------------------------
            # 3) JSON → dict 변환
            # -----------------------------
            try:
                data = json.loads(json_bytes.decode("utf-8"))
            except Exception:
                raise HTTPException(status_code=400, detail="JSON 파싱에 실패했습니다.")

            diaries_data = data.get("diaries", [])
            schedules_data = data.get("schedules", [])
            todos_data = data.get("todos", [])

            # =====================================================
            # 4) DB 전체 삭제 후 → ZIP 내용으로 갈아끼우기
            # =====================================================
            try:
                # 기존 데이터 모두 삭제
                db.query(Diary).delete()
                db.query(Schedule).delete()
                db.query(Todo).delete()
                db.commit()

                # -----------------------------
                # Diary 복원
                # -----------------------------
                for d in diaries_data:
                    # created_at 복원 (ISO 형식일 경우)
                    created_at = None
                    if d.get("created_at"):
                        try:
                            created_at = datetime.fromisoformat(d["created_at"])
                        except Exception:
                            created_at = None

                    # updated_at 복원 (Diary 모델엔 없지만, 혹시 모를 구버전 호환용)
                    updated_at = None
                    if d.get("updated_at"):
                        try:
                            updated_at = datetime.fromisoformat(d["updated_at"])
                        except Exception:
                            updated_at = None

                    diary = Diary(
                        title=d.get("title") or "",
                        content=d.get("content") or "",
                        image_url=d.get("image_url"),
                        tags=d.get("tags") or "",
                    )

                    # created_at이 있으면 덮어쓰기
                    if created_at:
                        diary.created_at = created_at

                    # Diary 모델에 updated_at 이 있다면(미래 확장 대비) 적용
                    if hasattr(diary, "updated_at") and updated_at:
                        diary.updated_at = updated_at

                    db.add(diary)

                # -----------------------------
                # Schedule 복원
                # -----------------------------
                for s in schedules_data:
                    sched = Schedule(
                        date=s.get("date") or "",
                        title=s.get("title") or "",
                        memo=s.get("memo"),
                        time_str=s.get("time_str"),
                        place=s.get("place"),
                        done=bool(s.get("done", False)),
                    )
                    db.add(sched)

                # -----------------------------
                # Todo 복원
                # -----------------------------
                for t in todos_data:
                    todo = Todo(
                        id=t.get("id"),
                        date=t.get("date") or "",
                        title=t.get("title") or "",
                        status=t.get("status") or "pending",
                        order=t.get("order") or 0,
                    )
                    db.add(todo)

                db.commit()

            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"DB 복원 중 오류 발생: {e}")

            # =====================================================
            # 5) 이미지 복원
            # =====================================================
            try:
                upload_dir: Path = UPLOAD_DIR
                upload_dir.mkdir(parents=True, exist_ok=True)

                # 현재는 '덮어쓰기' 방식.
                # ZIP 안의 파일만 새로 쓰고, 기존에 있던 파일은 지우지 않는다.
                # 필요하면 전체 삭제하는 로직 활성 가능.
                #
                # for old in upload_dir.rglob("*"):
                #     if old.is_file():
                #         old.unlink()

                # ZIP 에 포함된 uploads/* 파일을 그대로 저장
                for name in image_names:
                    # name = "uploads/파일명"
                    rel_path = name[len("uploads/"):]
                    if not rel_path:
                        continue

                    data_bytes = zf.read(name)

                    target_path = upload_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    with target_path.open("wb") as f:
                        f.write(data_bytes)

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"이미지 복원 중 오류 발생: {e}")

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="손상된 ZIP 파일입니다.")

    # 복원 완료 후 홈으로 이동
    return RedirectResponse(url="/", status_code=303)
