# routers/diary.py
from pathlib import Path
from datetime import datetime, date, timedelta
import json
import math
import shutil

from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from deps import (
    DATA_DIR,
    ITEMS_PER_PAGE_LIST,
    ITEMS_PER_PAGE_GALLERY,
    _normalize_entry,
    _parse_tags,
    load_entry,
    save_entry_json,
    delete_entry_json,
    templates,
)

router = APIRouter()


@router.get("/diary", response_class=HTMLResponse, name="diary_index")
async def diary_index(
    request: Request,
    range: str = "all",
    start: str | None = None,
    end: str | None = None,
    tag: str | None = None,
    page: int = 1,
    view: str = "list",
):
    """
    기록 목록 + 검색 화면
    """
    today = date.today()
    date_from: date | None = None
    date_to:   date | None = None

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

    all_entries: list[dict] = []

    for json_file in sorted(DATA_DIR.glob("*.json"), reverse=True):
        if json_file.name in ("schedule.json", "todos.json"):
            continue

        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data = _normalize_entry(data)

        created_str = data.get("created_at") or ""
        created_date: date | None = None
        if created_str:
            try:
                date_part = created_str.split(" ")[0]
                created_date = datetime.strptime(date_part, "%Y-%m-%d").date()
            except ValueError:
                created_date = None

        if date_from and created_date and created_date < date_from:
            continue
        if date_to and created_date and created_date > date_to:
            continue

        if tag:
            tags = data.get("tags") or []
            if isinstance(tags, str):
                tags = _parse_tags(tags)
            if tag not in tags:
                continue

        data["id"] = json_file.stem
        all_entries.append(data)

    per_page    = ITEMS_PER_PAGE_GALLERY if view == "gallery" else ITEMS_PER_PAGE_LIST
    total_items = len(all_entries)
    total_pages = max(1, math.ceil(total_items / per_page)) if total_items else 1

    page      = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    end_idx   = start_idx + per_page

    entries = all_entries[start_idx:end_idx]

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


@router.post("/save", response_class=RedirectResponse)
async def save_entry(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    tags: str = Form(""),
    photo: UploadFile | None = File(None),
    view: str = Form("list"),
    redirect_url: str | None = Form(None),
):
    """새 기록 저장"""
    from deps import UPLOAD_DIR  # 순환 import 피하려고 내부에서 import

    image_url = None

    if photo and photo.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(photo.filename).suffix
        filename = f"{ts}{ext}"
        save_path = UPLOAD_DIR / filename

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        image_url = f"/uploads/{filename}"

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = {
        "title": title,
        "content": content.replace("\r\n", "\n"),
        "image_url": image_url,
        "created_at": created_at,
        "tags": _parse_tags(tags),
    }

    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_entry_json(entry_id, entry)

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


@router.get("/entry/{entry_id}", response_class=HTMLResponse)
async def read_entry(
    request: Request,
    entry_id: str,
    view: str = "list",
):
    entry = load_entry(entry_id)
    entry["id"] = entry_id
    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "entry": entry,
            "view": view,
        },
    )


@router.get("/entry/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry_form(
    request: Request,
    entry_id: str,
    view: str = "list",
):
    entry = load_entry(entry_id)
    entry["id"] = entry_id
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
):
    from deps import UPLOAD_DIR

    entry = load_entry(entry_id)

    entry["title"] = title
    entry["content"] = content.replace("\r\n", "\n")
    entry["tags"] = _parse_tags(tags)
    entry["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if remove_image:
        entry["image_url"] = None

    if photo and photo.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(photo.filename).suffix
        filename = f"{entry_id}_{ts}{ext}"
        save_path = UPLOAD_DIR / filename

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        entry["image_url"] = f"/uploads/{filename}"

    save_entry_json(entry_id, entry)

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


@router.post("/entry/{entry_id}/delete")
async def delete_entry(
    entry_id: str,
    view: str = Form("list"),
    redirect_url: str | None = Form(None),
):
    delete_entry_json(entry_id)
    
    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


@router.get("/api/entry/{entry_id}")
async def api_get_entry(entry_id: str):
    """
    인라인 에디터(기록 탭 오른쪽)용 JSON API
    """
    entry = load_entry(entry_id)
    entry["id"] = entry_id
    return entry
