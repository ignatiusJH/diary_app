# main.py
from datetime import date, timedelta
import calendar
import logging
from sqlalchemy import text   # ← 이거 추가


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
    require_auth,   # 전역 Basic 인증
)
from routers import (
    diary_router,
    schedule_router,
    todos_router,
    stats_router,
    backup_router,
    restore_router,
)

# =========================
# DB 관련 (Render / SQLAlchemy)
# =========================
from db import Base, engine
import models  # Diary / Schedule / Todo 모델이 들어있는 models.py

logger = logging.getLogger("steplog")


# =========================
# 앱 & 공통 설정
# =========================

app = FastAPI(
    dependencies=[Depends(require_auth)]
)

# 정적 파일
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static",  StaticFiles(directory=STATIC_DIR),  name="static")

# 라우터
app.include_router(diary_router)
app.include_router(schedule_router)
app.include_router(todos_router)
app.include_router(stats_router)
app.include_router(backup_router)
app.include_router(restore_router)


# =========================
# 앱 시작 시: 테이블 자동 생성 + 컬럼 보정
# =========================
@app.on_event("startup")
async def on_startup():
    logger.info(">>> STARTUP: creating DB tables via Base.metadata.create_all")
    import models  # 모델 등록

    # 테이블 없으면 생성 (있으면 건들지 않음)
    Base.metadata.create_all(bind=engine)

    # ---- 여기서부터 1회성 마이그레이션 ----
    # Postgres 의 todos 테이블에 sort_index 컬럼이 없으면 추가
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE todos "
                    "ADD COLUMN IF NOT EXISTS sort_index INTEGER"
                )
            )
        logger.info(">>> STARTUP: ensured todos.sort_index column exists")
    except Exception as e:
        logger.error(">>> STARTUP: failed to ensure todos.sort_index: %s", e)



# =========================
# 메인 대시보드 ("/")
# =========================
@app.get("/", response_class=HTMLResponse, name="home")
async def dashboard(request: Request):
    today = date.today()
    today_str = today.isoformat()

    # ---- 일정 ----
    schedule_items = load_schedule()
    horizon = today + timedelta(days=15)
    upcoming = [
        item for item in schedule_items
        if today_str <= item.date <= horizon.isoformat()
    ]
    upcoming_sorted = sorted(upcoming, key=schedule_sort_key)

    # ---- 오늘 체크리스트 (진행중만) ----
    todos = load_todos()
    today_todos = [t for t in todos if t.status == "pending"]

    # ---- 달력 데이터 ----
    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
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

    # 디버그용 로그 (필요없으면 주석처리해도 됨)
    logger.info(
        "DASHBOARD_DEBUG: schedules_total=%d upcoming_shown=%d "
        "todos_total=%d pending_shown=%d",
        len(schedule_items),
        len(upcoming_sorted),
        len(todos),
        len(today_todos),
    )

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
