# routers/schedule.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from deps import (
    templates,
)
from db import get_db
from models import Schedule

router = APIRouter()


# -----------------------------
# 헬퍼: Schedule → dict
# -----------------------------
def _schedule_to_dict(row: Schedule) -> dict:
    return {
        "id": str(row.id),
        "date": row.date,
        "title": row.title,
        "memo": row.memo,
        "time": row.time_str,       # 예전 ScheduleItem 호환
        "time_str": row.time_str,
        "place": row.place,
        "done": row.done,
    }


# =========================
# 1) 일정 목록 화면
# =========================
@router.get("/schedule", response_class=HTMLResponse, name="schedule_page")
async def schedule_page(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    일정 목록 화면
    - 기본: '오늘 이후' 일정만 보여준다. (오늘보다 이전 날짜는 숨김)
    - start, end 파라미터로 추가 필터링 가능
    """
    today = date.today()
    today_str = today.isoformat()

    query = db.query(Schedule)

    # 오늘 이후만
    query = query.filter(Schedule.date >= today_str)

    # 선택 기간 필터
    if start:
        try:
            start_date = date.fromisoformat(start)
            query = query.filter(Schedule.date >= start_date.isoformat())
        except ValueError:
            start_date = None
    else:
        start_date = None

    if end:
        try:
            end_date = date.fromisoformat(end)
            query = query.filter(Schedule.date <= end_date.isoformat())
        except ValueError:
            end_date = None
    else:
        end_date = None

    # 날짜 + 제목 기준 정렬
    rows = (
        query
        .order_by(Schedule.date.asc(), Schedule.title.asc())
        .all()
    )

    items = [_schedule_to_dict(r) for r in rows]

    return templates.TemplateResponse(
        "schedule.html",
        {
            "request": request,
            "items": items,
            "start": start,
            "end": end,
            "year": today.year,
            "month": today.month,
            "today_str": today_str,
        },
    )


# =========================
# 2) 일정 생성 폼
# =========================
@router.get("/schedule/new", response_class=HTMLResponse, name="new_schedule_form")
async def new_schedule_form(request: Request):
    """일정 생성 폼"""
    today_str = date.today().isoformat()
    return templates.TemplateResponse(
        "schedule_form.html",
        {
            "request": request,
            "default_date": today_str,
        },
    )


# =========================
# 3) 일정 생성 처리
# =========================
@router.post("/schedule/new")
async def create_schedule(
    request: Request,
    date_str: str = Form(...),
    title: str = Form(...),
    memo: str = Form(""),
    time_str: str = Form(""),
    place: str = Form(""),
    db: Session = Depends(get_db),
):
    """일정 생성 처리"""
    item = Schedule(
        date=date_str,
        title=title,
        memo=memo or None,
        time_str=time_str or None,
        place=place or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return RedirectResponse(url="/schedule", status_code=303)


# =========================
# 4) 일정 수정 처리
# =========================
@router.post("/schedule/{schedule_id}/update", response_class=RedirectResponse)
async def update_schedule(
    schedule_id: str,
    date_str: str = Form(...),
    title: str = Form(...),
    memo: str = Form(""),
    time_str: str = Form(""),
    place: str = Form(""),
    db: Session = Depends(get_db),
):
    """일정 수정 처리"""
    item = db.get(Schedule, int(schedule_id))
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")

    item.date = date_str
    item.title = title
    item.memo = memo or None
    item.time_str = time_str or None
    item.place = place or None

    db.add(item)
    db.commit()

    return RedirectResponse(url="/schedule", status_code=303)


# =========================
# 5) 일정 삭제
# =========================
@router.post("/schedule/{schedule_id}/delete", response_class=RedirectResponse)
async def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
):
    """일정 삭제"""
    item = db.get(Schedule, int(schedule_id))
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(item)
    db.commit()

    return RedirectResponse(url="/schedule", status_code=303)


# =========================
# 6) JSON API (인라인 에디터용)
# =========================
@router.get("/api/schedule/{schedule_id}")
async def api_get_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
):
    """일정 탭 오른쪽 인라인 에디터용 JSON API"""
    item = db.get(Schedule, int(schedule_id))
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return _schedule_to_dict(item)
