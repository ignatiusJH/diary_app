# main.py
from datetime import date, timedelta
import calendar

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from deps import (
    UPLOAD_DIR,
    STATIC_DIR,
    load_schedule,
    load_todos,
    schedule_sort_key,
    templates,
    owner_only,   # ✅ 추가
    require_auth,
)
from routers import (
    diary_router,
    schedule_router,
    todos_router,
    stats_router,
)

# 여기에서 전체 보호를 한 번에 건다
app = FastAPI(
    dependencies=[Depends(require_auth)]  # ✅ 모든 엔드포인트에 인증 강제
)

# 정적 파일 mount
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static",  StaticFiles(directory=STATIC_DIR),  name="static")

# 라우터 등록
app.include_router(diary_router)
app.include_router(schedule_router)
app.include_router(todos_router)
app.include_router(stats_router)


# 메인 대시보드 ("/")
@app.get("/", response_class=HTMLResponse, name="home")
async def dashboard(request: Request):
    today = date.today()
    today_str = today.isoformat()

    schedule_items = load_schedule()
    horizon = today + timedelta(days=15)
    upcoming = [
        item for item in schedule_items
        if today_str <= item.date <= horizon.isoformat()
    ]
    upcoming_sorted = sorted(upcoming, key=schedule_sort_key)

    todos = load_todos()
    today_todos = [
        t for t in todos
        if t.status == "pending"
    ]

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
