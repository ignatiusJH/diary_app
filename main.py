# main.py
from datetime import date, timedelta
import calendar

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from deps import (
    UPLOAD_DIR,
    STATIC_DIR,
    load_schedule,
    load_todos,
    schedule_sort_key,
    templates,
    owner_only,   # ✅ 주인 인증
    require_auth, # ✅ 전역 Basic 인증
    DB_PATH,      # ✅ SQLite 파일 경로
)
from routers import (
    diary_router,
    schedule_router,
    todos_router,
    stats_router,
    backup_router,   # 있어도 됨 (나중에 라우터 정리할 때 쓸 수 있음)
    restore_router,
)

# 여기에서 전체 보호를 한 번에 건다
app = FastAPI(
    dependencies=[Depends(require_auth)]  # ✅ 모든 엔드포인트에 기본 인증 강제
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
# DB 백업 엔드포인트 (직접 추가)
# =========================
@app.get("/backup/db", dependencies=[Depends(owner_only)])
async def backup_db():
    """
    steplog.db 파일을 그대로 다운로드해 주는 백업 엔드포인트.
    통계 화면 오른쪽 아래 버튼에서 이 URL을 호출한다.
    """
    db_path = DB_FILE

    if not db_path.exists():
        raise HTTPException(status_code=404, detail="DB 파일을 찾을 수 없습니다.")

    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"steplog_backup_{ts}.db"

    return FileResponse(
        path=str(db_path),
        media_type="application/octet-stream",
        filename=filename,
    )


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
