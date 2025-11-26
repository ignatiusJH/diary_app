# routers/schedule.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from deps import (
    load_schedule,
    save_schedule,
    schedule_sort_key,
    ScheduleItem,
    templates,
)

router = APIRouter()


@router.get("/schedule", response_class=HTMLResponse, name="schedule_page")
async def schedule_page(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """
    일정 목록 화면
    - 기본: '오늘 이후' 일정만 보여준다. (오늘보다 이전 날짜는 숨김)
    - 필요한 경우 start, end 파라미터로 추가 필터링 가능
    """
    today = date.today()
    today_str = today.isoformat()

    items = load_schedule()

    # 1) 기본 정렬
    items_sorted = sorted(items, key=schedule_sort_key)

    # 2) 오늘 이전 일정은 기본적으로 숨김
    items_sorted = [
        it for it in items_sorted
        if date.fromisoformat(it.date) >= today
    ]

    # 3) 선택 기간 필터 (있다면 추가로 좁히기)
    if start:
        try:
            start_date = date.fromisoformat(start)
            items_sorted = [
                it for it in items_sorted
                if date.fromisoformat(it.date) >= start_date
            ]
        except ValueError:
            start_date = None
    else:
        start_date = None

    if end:
        try:
            end_date = date.fromisoformat(end)
            items_sorted = [
                it for it in items_sorted
                if date.fromisoformat(it.date) <= end_date
            ]
        except ValueError:
            end_date = None
    else:
        end_date = None

    return templates.TemplateResponse(
        "schedule.html",
        {
            "request": request,
            "items": items_sorted,
            "start": start,
            "end": end,
            "year": today.year,
            "month": today.month,
            "today_str": today_str,
        },
    )


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


@router.post("/schedule/new")
async def create_schedule(
    request: Request,
    date_str: str = Form(...),
    title: str = Form(...),
    memo: str = Form(""),
    time_str: str = Form(""),
    place: str = Form(""),
):
    """일정 생성 처리"""
    items = load_schedule()
    new_item = ScheduleItem(
        id=str(len(items) + 1),
        date=date_str,
        title=title,
        memo=memo or None,
        time=time_str or None,
        time_str=time_str or None,
        place=place or None,
    )
    items.append(new_item)
    save_schedule(items)
    return RedirectResponse(url="/schedule", status_code=303)


@router.post("/schedule/{schedule_id}/update", response_class=RedirectResponse)
async def update_schedule(
    schedule_id: str,
    date_str: str = Form(...),
    title: str = Form(...),
    memo: str = Form(""),
    time_str: str = Form(""),
    place: str = Form(""),
):
    """일정 수정 처리"""
    items = load_schedule()
    for item in items:
        if item.id == schedule_id:
            item.date = date_str
            item.title = title
            item.memo = memo or None
            item.time = time_str or None
            item.time_str = time_str or None
            item.place = place or None
            break
    save_schedule(items)
    return RedirectResponse(url="/schedule", status_code=303)


@router.post("/schedule/{schedule_id}/delete", response_class=RedirectResponse)
async def delete_schedule(schedule_id: str):
    """일정 삭제"""
    items = load_schedule()
    items = [it for it in items if it.id != schedule_id]
    save_schedule(items)
    return RedirectResponse(url="/schedule", status_code=303)


@router.get("/api/schedule/{schedule_id}")
async def api_get_schedule(schedule_id: str):
    """일정 탭 오른쪽 인라인 에디터용 JSON API"""
    items = load_schedule()
    for item in items:
        if item.id == schedule_id:
            return item
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Schedule not found")
