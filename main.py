# main.py
from datetime import date, timedelta
import calendar
from types import SimpleNamespace

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from deps import (
    UPLOAD_DIR,
    STATIC_DIR,
    templates,
    require_auth,
)
from routers import (
    diary_router,
    schedule_router,
    todos_router,
    stats_router,
    backup_router,   # ✅ /backup/db (ZIP) 은 여기에서 처리
    restore_router,  # ✅ /restore/db (ZIP 업로드) 도 여기에서 처리
)

from db import get_db
from models import Schedule, Todo

# =========================
# 앱 & 공통 설정
# =========================

# 전체 엔드포인트에 인증 한 번에 걸기
app = FastAPI(
    dependencies=[Depends(require_auth)]
)

# 정적 파일 mount
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static",  StaticFiles(directory=STATIC_DIR),  name="static")

# 라우터 등록
app.include_router(diary_router)
app.include_router(schedule_router)
app.include_router(todos_router)
app.include_router(stats_router)
app.include_router(backup_router)
app.include_router(restore_router)


# =========================
# 메인 대시보드 ("/")
# =========================
@app.get("/", response_class=HTMLResponse, name="home")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    today = date.today()
    today_str = today.isoformat()

    # ----- 일정: DB에서 모두 가져와서 예전 ScheduleItem 과 비슷한 형태로 변환 -----
    rows = db.query(Schedule).all()
    schedule_items = [
        SimpleNamespace(
            id=str(r.id),
            date=r.date,             # "YYYY-MM-DD"
            title=r.title,
            memo=r.memo,
            time=r.time_str,         # 템플릿 호환용
            time_str=r.time_str,
            place=r.place,
            done=r.done,
        )
        for r in rows
    ]

    # 15일 이내 일정만 "다가오는 일정"으로 표시
    horizon = today + timedelta(days=15)
    upcoming = [
        item for item in schedule_items
        if (item.date is not None)
        and (today_str <= item.date <= horizon.isoformat())
    ]
    # 날짜, 제목 기준 정렬
    upcoming_sorted = sorted(upcoming, key=lambda it: (it.date, it.title or ""))

    # ----- 오늘 체크리스트 (기존 JSON/파일 기반 그대로) -----
    today_todos = (
    db.query(Todo)
    .filter(Todo.status == "pending")
    .order_by(Todo.order.asc(), Todo.date.asc())
    .all()
)
    # ----- 달력 데이터 (해당 달에 일정이 있는 날 표시) -----
    cal = calendar.Calendar(firstweekday=6)
    weeks = []
    for week in cal.monthdatescalendar(today.year, today.month):
        week_data = []
        for d in week:
            key = d.isoformat()
            week_data.append({
                "day": d.day,
                "in_month": (d.month == today.month),
                "has_schedule": any(it.date == key for it in schedule_items),
                "is_today": (d == today),
            })
        weeks.append(week_data)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "year": today.year,
            "month": today.month,
            "weeks": weeks,
            "upcoming_items": upcoming_sorted,
            "today_todos": today_todos,
            "today_str": today_str,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
