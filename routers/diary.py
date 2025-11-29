# routers/diary.py
# ---------------------------------------------------------
# "일기(Diary)" 기능 전체를 담당하는 라우터.
#
# 주요 기능:
#   1) /diary           : 목록 + 검색(기간, 태그, 뷰모드)
#   2) /save            : 새 일기 저장
#   3) /entry/{id}      : 상세보기
#   4) /entry/{id}/edit : 수정 폼
#   5) /entry/{id}/edit : 수정 제출
#   6) /entry/{id}/delete : 삭제
#   7) /api/entry/{id}  : JSON API (인라인 에디터용)
# ---------------------------------------------------------

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
    ITEMS_PER_PAGE_LIST,     # 리스트 뷰 페이지당 개수
    ITEMS_PER_PAGE_GALLERY,  # 갤러리 뷰 페이지당 개수
    _parse_tags,             # "운동, 공부" → ["운동", "공부"]
    templates,               # Jinja 템플릿 엔진
)
from db import get_db
from models import Diary

# 이 파일에서 사용할 라우터 객체 생성
router = APIRouter()


# -------------------------------------------------
# 헬퍼 함수: Diary ORM 객체 → 템플릿용 dict 로 변환
# -------------------------------------------------
def _diary_to_dict(row: Diary) -> dict:
    """
    Diary ORM 객체를 템플릿/JSON에서 쓰기 편한 dict 형태로 변환한다.
    - created_at 은 "YYYY-MM-DD HH:MM" 문자열로 변환
    - tags 는 문자열(쉼표 구분)을 리스트로 변환
    """
    return {
        "id": str(row.id),
        "title": row.title,
        "content": row.content,
        "image_url": row.image_url,
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "",
        "tags": _parse_tags(row.tags or ""),
    }


# =================================================
# 1) 기록 목록 + 검색
# =================================================
@router.get("/diary", response_class=HTMLResponse, name="diary_index")
async def diary_index(
    request: Request,
    range: str = "all",         # 기간 필터 (today, yesterday, week, month, custom, all)
    start: str | None = None,   # custom 모드일 때 시작일(YYYY-MM-DD)
    end: str | None = None,     # custom 모드일 때 종료일(YYYY-MM-DD)
    tag: str | None = None,     # 태그 필터
    page: int = 1,              # 페이지 번호
    view: str = "list",         # list / gallery
    db: Session = Depends(get_db),
):
    """
    기록 목록 + 검색 화면
    - 기간(range) / 태그(tag) / 뷰(view) / 페이지(page) 를 기준으로 목록을 보여준다.
    """
    today = date.today()
    date_from: date | None = None
    date_to: date | None = None

    # -----------------------------
    # 기간 계산 (range 값에 따라)
    # -----------------------------
    if range == "today":
        # 오늘 하루만
        date_from = date_to = today
    elif range == "yesterday":
        y = today - timedelta(days=1)
        date_from = date_to = y
    elif range == "week":
        # 이번 주 월요일 ~ 오늘
        start_of_week = today - timedelta(days=today.weekday())
        date_from = start_of_week
        date_to = today
    elif range == "month":
        # 이번 달 1일 ~ 오늘
        start_of_month = date(today.year, today.month, 1)
        date_from = start_of_month
        date_to = today
    elif range == "custom":
        # 사용자가 직접 입력한 기간 사용
        if start:
            date_from = datetime.strptime(start, "%Y-%m-%d").date()
        if end:
            date_to = datetime.strptime(end, "%Y-%m-%d").date()
    # range == "all" 이면 date_from/date_to 둘 다 None → 전체

    # -----------------------------
    # 기본 쿼리 (SELECT * FROM diaries)
    # -----------------------------
    query = db.query(Diary)

    # 날짜 필터 (created_at 을 날짜 범위로 필터)
    if date_from:
        dt_from = datetime.combine(date_from, datetime.min.time())
        query = query.filter(Diary.created_at >= dt_from)
    if date_to:
        dt_to = datetime.combine(date_to, datetime.max.time())
        query = query.filter(Diary.created_at <= dt_to)

    # 태그 필터 (단순 LIKE 검색: "운동" 포함된 것 등)
    if tag:
        query = query.filter(Diary.tags.contains(tag))

    # 최신순 정렬 (created_at DESC)
    query = query.order_by(Diary.created_at.desc())

    # 뷰 타입에 따라 페이지당 개수 결정
    per_page = ITEMS_PER_PAGE_GALLERY if view == "gallery" else ITEMS_PER_PAGE_LIST

    # 전체 개수 / 총 페이지 계산
    total_items = query.count()
    total_pages = max(1, math.ceil(total_items / per_page)) if total_items else 1

    # page 범위 보정 (1 ~ total_pages)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page

    # 실제로 해당 페이지에 들어갈 레코드만 가져오기
    rows = query.offset(start_idx).limit(per_page).all()
    entries = [_diary_to_dict(r) for r in rows]

    # diary.html 템플릿 렌더링
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


# =================================================
# 2) 새 기록 저장
# =================================================
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
    """
    새 기록(일기) 한 개를 저장하는 엔드포인트.
    - 이미지 업로드
    - 태그 문자열 정리
    - DB INSERT
    """
    # 순환 import 방지를 위해 함수 내부에서 import
    from deps import UPLOAD_DIR

    image_url: str | None = None

    # -----------------------------
    # 이미지 업로드 처리
    # -----------------------------
    if photo and photo.filename:
        # 파일 이름: 타임스탬프 기반 (충돌 방지)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(photo.filename).suffix
        filename = f"{ts}{ext}"
        save_path = UPLOAD_DIR / filename

        # 업로드된 파일을 디스크에 저장
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        # 템플릿/브라우저에서 접근할 수 있는 URL
        image_url = f"/uploads/{filename}"

    # -----------------------------
    # 태그 문자열 정리
    # -----------------------------
    tags_list = _parse_tags(tags)  # "운동, 공부" → ["운동","공부"]
    tags_str = ", ".join(tags_list) if tags_list else ""

    # -----------------------------
    # DB 저장 (Diary INSERT)
    # -----------------------------
    diary = Diary(
        title=title,
        content=content.replace("\r\n", "\n"),  # 줄바꿈을 \n 으로 통일
        image_url=image_url,
        tags=tags_str,
    )
    db.add(diary)
    db.commit()
    db.refresh(diary)  # INSERT 후 생성된 id 등을 다시 객체에 반영

    # 저장 후 돌아갈 위치 (리다이렉트)
    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


# =================================================
# 3) 단일 기록 상세보기
# =================================================
@router.get("/entry/{entry_id}", response_class=HTMLResponse)
async def read_entry(
    request: Request,
    entry_id: str,
    view: str = "list",
    db: Session = Depends(get_db),
):
    """
    단일 일기 상세보기 페이지.
    """
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


# =================================================
# 4) 수정 폼
# =================================================
@router.get("/entry/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry_form(
    request: Request,
    entry_id: str,
    view: str = "list",
    db: Session = Depends(get_db),
):
    """
    수정 폼 페이지.
    - 현재 내용을 불러와서 form에 채워 넣어준다.
    """
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = _diary_to_dict(diary)
    # 텍스트박스에 보여줄 태그 문자열 ("운동, 공부")
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


# =================================================
# 5) 수정 제출
# =================================================
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
    """
    수정 내용 제출 처리.
    - 제목/내용/태그 수정
    - 기존 이미지 삭제/유지/새 이미지로 교체
    """
    from deps import UPLOAD_DIR

    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    # 텍스트 필드 업데이트
    diary.title = title
    diary.content = content.replace("\r\n", "\n")

    tags_list = _parse_tags(tags)
    diary.tags = ", ".join(tags_list) if tags_list else ""

    # -----------------------------
    # 이미지 삭제 옵션
    # -----------------------------
    if remove_image:
        diary.image_url = None

    # -----------------------------
    # 새 이미지 업로드 (있을 경우)
    # -----------------------------
    if photo and photo.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(photo.filename).suffix
        # entry_id 를 파일 이름에 포함시켜 어떤 글의 이미지인지 추적 가능하게 함
        filename = f"{entry_id}_{ts}{ext}"
        save_path = UPLOAD_DIR / filename

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        diary.image_url = f"/uploads/{filename}"

    db.add(diary)
    db.commit()

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


# =================================================
# 6) 삭제
# =================================================
@router.post("/entry/{entry_id}/delete")
async def delete_entry(
    entry_id: str,
    view: str = Form("list"),
    redirect_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """
    일기 한 개 삭제.
    """
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    db.delete(diary)
    db.commit()

    target = redirect_url or f"/diary?view={view}"
    return RedirectResponse(url=target, status_code=303)


# =================================================
# 7) JSON API (인라인 에디터용)
# =================================================
@router.get("/api/entry/{entry_id}")
async def api_get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
):
    """
    인라인 에디터(기록 탭 오른쪽)에 쓰이는 JSON API.

    - 화면에서 fetch("/api/entry/123") 같은 식으로 호출해서
      JSON 데이터를 받아서 바로 에디터에 채워 넣는 용도.
    """
    diary = db.get(Diary, int(entry_id))
    if not diary:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = _diary_to_dict(diary)
    return entry
