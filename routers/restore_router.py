# routers/restore_router.py
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
from deps import UPLOAD_DIR  # <- 이미지 폴더

router = APIRouter()


@router.post("/restore/db", response_class=RedirectResponse)
async def restore_db(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    /backup/db 에서 받은 steplog_backup.zip 을 업로드하면
    DB(Diary, Schedule, Todo) + /uploads 이미지를 통째로 갈아끼운다.

    ⚠ 기존 DB 데이터는 모두 삭제되고, ZIP 내용으로 대체된다.
    ⚠ /uploads 안의 기존 파일들도 ZIP 기준으로 다시 채운다고 보는 게 안전하다.
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="ZIP 파일을 업로드해주세요.")

    content = await file.read()

    try:
        mem_file = io.BytesIO(content)
        with zipfile.ZipFile(mem_file, mode="r") as zf:
            namelist = zf.namelist()

            if "steplog_backup.json" not in namelist:
                raise HTTPException(
                    status_code=400,
                    detail="steplog_backup.json 이 포함된 백업 ZIP이 아닙니다.",
                )

            json_bytes = zf.read("steplog_backup.json")

            # 이미지 파일 목록 (uploads/로 시작하는 것들)
            image_names = [name for name in namelist if name.startswith("uploads/")]

            # 먼저 JSON 파싱
            try:
                data = json.loads(json_bytes.decode("utf-8"))
            except Exception:
                raise HTTPException(status_code=400, detail="JSON 파싱에 실패했습니다.")

            diaries_data = data.get("diaries", [])
            schedules_data = data.get("schedules", [])
            todos_data = data.get("todos", [])

            # 1) DB 갈아끼우기
            try:
                db.query(Diary).delete()
                db.query(Schedule).delete()
                db.query(Todo).delete()
                db.commit()

                # Diary 복원
                for d in diaries_data:
                    created_at = None
                    if d.get("created_at"):
                        try:
                            created_at = datetime.fromisoformat(d["created_at"])
                        except Exception:
                            created_at = None

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
                    if created_at:
                        diary.created_at = created_at
                    if hasattr(diary, "updated_at") and updated_at:
                        diary.updated_at = updated_at

                    db.add(diary)

                # Schedule 복원
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

                # Todo 복원
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

            # 2) 이미지 파일 복원 (/uploads 폴더)
            try:
                upload_dir: Path = UPLOAD_DIR
                upload_dir.mkdir(parents=True, exist_ok=True)

                # 기존 파일을 전부 지울지 말지는 선택인데,
                # 백업 기준으로 맞추려면 지우는 게 맞다.
                # 일단은 지우지 않고 '덮어쓰기' 방식으로 갈게.
                # 필요하면 아래 주석 풀어서 전체 삭제 가능.
                #
                # for old in upload_dir.rglob("*"):
                #     if old.is_file():
                #         old.unlink()

                for name in image_names:
                    # name 예: "uploads/20251128_123456.png"
                    rel_path = name[len("uploads/") :]  # "20251128_123456.png"
                    if not rel_path:
                        continue

                    data_bytes = zf.read(name)

                    target_path = upload_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    with target_path.open("wb") as f:
                        f.write(data_bytes)

            except Exception as e:
                # 이미지 복원만 실패해도 앱은 돌아가게, 여기선 경고만 던지고 끝낼 수도 있는데
                # 일단은 에러로 보고 HTTPException 던진다.
                raise HTTPException(status_code=500, detail=f"이미지 복원 중 오류 발생: {e}")

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="손상된 ZIP 파일입니다.")

    return RedirectResponse(url="/", status_code=303)
