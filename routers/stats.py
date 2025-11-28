# routers/stats.py
from datetime import date

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from deps import templates
from db import get_db
from models import Todo

router = APIRouter()


@router.get("/stats", response_class=HTMLResponse, name="stats_page")
async def stats_page(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
):
    # ----- 1) 전체 To-do 조회 -----
    rows = (
        db.query(Todo)
        .order_by(Todo.date.asc())
        .all()
    )

    if not rows:
        # 데이터가 하나도 없을 때
        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "overall_total": 0,
                "overall_done": 0,
                "overall_giveup": 0,
                "overall_pending": 0,
                "overall_done_rate": 0.0,
                "overall_gaveup_rate": 0.0,
                "start": None,
                "end": None,
                "range_total": 0,
                "range_done": 0,
                "range_giveup": 0,
                "range_pending": 0,
                "range_done_rate": 0.0,
                "range_gaveup_rate": 0.0,
            },
        )

    # rows 는 Todo 객체 리스트
    items = rows

    # ----- 2) 전체 구간 통계 -----
    overall_total   = len(items)
    overall_done    = sum(1 for it in items if it.status == "done")
    overall_giveup  = sum(1 for it in items if it.status == "giveup")
    overall_pending = sum(1 for it in items if it.status == "pending")

    if overall_total > 0:
        overall_done_rate   = round(overall_done / overall_total * 100, 1)
        overall_gaveup_rate = round(overall_giveup / overall_total * 100, 1)
    else:
        overall_done_rate = overall_gaveup_rate = 0.0

    # ----- 3) 기간 기본값 (최초 ~ 마지막 날짜) -----
    all_dates = sorted({it.date for it in items})
    default_start = date.fromisoformat(all_dates[0])
    default_end   = date.fromisoformat(all_dates[-1])

    if start:
        start_date = date.fromisoformat(start)
    else:
        start_date = default_start

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = default_end

    # ----- 4) 선택 구간 통계 -----
    def in_range(it: Todo) -> bool:
        d = date.fromisoformat(it.date)
        return (d >= start_date) and (d <= end_date)

    ranged = [it for it in items if in_range(it)]

    range_total   = len(ranged)
    range_done    = sum(1 for it in ranged if it.status == "done")
    range_giveup  = sum(1 for it in ranged if it.status == "giveup")
    range_pending = sum(1 for it in ranged if it.status == "pending")

    if range_total > 0:
        range_done_rate   = round(range_done / range_total * 100, 1)
        range_gaveup_rate = round(range_giveup / range_total * 100, 1)
    else:
        range_done_rate = range_gaveup_rate = 0.0

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "overall_total": overall_total,
            "overall_done": overall_done,
            "overall_giveup": overall_giveup,
            "overall_pending": overall_pending,
            "overall_done_rate": overall_done_rate,
            "overall_gaveup_rate": overall_gaveup_rate,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "range_total": range_total,
            "range_done": range_done,
            "range_giveup": range_giveup,
            "range_pending": range_pending,
            "range_done_rate": range_done_rate,
            "range_gaveup_rate": range_gaveup_rate,
        },
    )
