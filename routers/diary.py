# routers/diary.py
from pathlib import Path
from datetime import datetime, date, timedelta
import math
import shutil

from fastapi import (
    APIRouter,
    Request,
    Form,
    UploadFile,
    File,
    HTTPException,
    Depends,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from deps import (
    ITEMS_PER_PAGE_LIST,
    ITEMS_PER_PAGE_GALLERY,
    _parse_tags,
    templates,
)
from db import get_db
from models import Diary

router = APIRouter()


# -----------------------------
# 헬퍼: Diary 모델 → 템플릿용 dict
# -----------------------------
def _diary_to_dict(row: Diary) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "content": row.content,
        "image_url": row.image_url,
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "",
        "tags": _parse_tags(row.tags or ""),
    }


# =========================
# 1) 기록 목록 + 검색
# =========================
@router.get("/diary", response_class=HTMLResponse, name="diary_index")
async def diary_index(
    request: Request,
    range: str = "all",
    start: str | None = None,
    end: str | None = None,
    tag: str | None = None,
    page: int = 1,
    view: str = "list",
    db: Session = Depends(get_db),
):
    """
    기록 목록 + 검색 화면
    """
    today = date.today()
    date_from: date | None = None
    date_to: date | None = None

    # 기간 계산
    if range == "today":
        date_from = date_to = today
    elif range == "yesterday":
        y = today - timedelta(days=1)
        date_from = date_to = y
    elif range == "week":
        start_of_week = today - timedelta(days=today.weekday())
        date_from = start_of_week
        date_to = today
    elif range == "month":
        start_of_month = date(today.year, today.month, 1)
        date_from = start_of_month
        date_to = today
    elif range == "custom":
        if start:
            date_from = datetime.strptime(start, "%Y-%m-%d").date()
        if end:
            date_to = datetime.strptime(end, "%Y-%m-%d").date()

    # 기본 쿼리
    query = db.query(Diary)

    # 날짜 필터 (created_at 을 날짜 범위로 필터)
    if date_from:
        dt_from = datetime.combine(date_from, datetime.min.time())
        query = query.filter(Diary.created_at >= dt_from)
    if date_to:
        dt_to = datetime.combine(date_to, datetime.max.time())
        query = query.filter(Diary.created_at <= dt_to)

    # 태그 필터 (단순 LIKE)
    if tag:
        query = query.filter(Diary.tags.contains(tag))

    # 최신순 정렬
    query = query.order_by(Diary.created_at.desc())

    per_page = ITEMS_PER_PAGE_GALLERY if view == "gallery" else ITEMS_PER_PAGE_LIST

    total_items = query.count()
    total_pages = max(1, math.ceil(total_items / per_page)) if total_items else 1

    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page

    rows = query.offset(start_idx).limit(per_page).all()
    entries = [_diary_to_dict(r) for r in rows]

    return templates.TemplateResponse(
        "diary.html",
        {
            "request": request,
            "entries": entries,
            "current_range": range,
            "start": start,
            "end": end,
            "tag": tag,
            "view": view,
            "page": page,
            "total_pages": total_pages,
        },
    )


# =========================
# 2) 새 기록 저장
# =========================
@router.post("/save", response_class=RedirectResponse)
async def save_entry(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    tags: str = Form(""),
    photo: UploadFile | None = File(None),
    view: str = Form("list"),
    redirect_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """새 기록 저장"""
    from deps import UPLOAD_DIR  # 순환 import 피하려고 내부에서 import

    image_url: str | None = None

    # 이미지 업로드
    if photo and photo.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(photo.filename).suffix
        filename = f"{ts}{ext}"
        save_path = UPLOAD_DIR / filename

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        image_url = f"/uploads/{filename}"

    # 태그 정리 (리스트 -> 문자열)
    tags_list = _parse_tags(tags)
    tags_str = ", ".join(tags_list) if tags_list else ""

    # DB 저장
    diary = Diary(
        title=title,
        content=content.replace("\r\n", "\n"),
        image_url=image_url,
        tags=tags_str,
    )
    db.add(diary)
    db.commit()
    db.refresh(diary)

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


# =========================
# 3) 단일 기록 상세보기
# =========================
@router.get("/entry/{entry_id}", response_class=HTMLResponse)
async def read_entry(
    request: Request,
    entry_id: str,
    view: str = "list",
    db: Session = Depends(get_db),
):
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = _diary_to_dict(diary)

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "entry": entry,
            "view": view,
        },
    )


# =========================
# 4) 수정 폼
# =========================
@router.get("/entry/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry_form(
    request: Request,
    entry_id: str,
    view: str = "list",
    db: Session = Depends(get_db),
):
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = _diary_to_dict(diary)
    tags_str = ", ".join(entry.get("tags", []))

    return templates.TemplateResponse(
        "edit_entry.html",
        {
            "request": request,
            "entry": entry,
            "tags_str": tags_str,
            "view": view,
        },
    )


# =========================
# 5) 수정 제출
# =========================
@router.post("/entry/{entry_id}/edit")
async def edit_entry_submit(
    entry_id: str,
    title: str = Form(...),
    content: str = Form(...),
    tags: str = Form(""),
    view: str = Form("list"),
    photo: UploadFile | None = File(None),
    remove_image: str | None = Form(None),
    redirect_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    from deps import UPLOAD_DIR

    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    diary.title = title
    diary.content = content.replace("\r\n", "\n")

    tags_list = _parse_tags(tags)
    diary.tags = ", ".join(tags_list) if tags_list else ""

    # 이미지 삭제
    if remove_image:
        diary.image_url = None

    # 새 이미지 업로드
    if photo and photo.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(photo.filename).suffix
        filename = f"{entry_id}_{ts}{ext}"
        save_path = UPLOAD_DIR / filename

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        diary.image_url = f"/uploads/{filename}"

    db.add(diary)
    db.commit()

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


# =========================
# 6) 삭제
# =========================
@router.post("/entry/{entry_id}/delete")
async def delete_entry(
    entry_id: str,
    view: str = Form("list"),
    redirect_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    db.delete(diary)
    db.commit()

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


# =========================
# 7) JSON API (인라인 에디터용)
# =========================
@router.get("/api/entry/{entry_id}")
async def api_get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
):
    """
    인라인 에디터(기록 탭 오른쪽)용 JSON API
    """
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = _diary_to_dict(diary)
    return entry
