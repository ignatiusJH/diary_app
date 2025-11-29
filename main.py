# main.py

# 날짜/시간 관련 표준 라이브러리
from datetime import date, timedelta
import calendar
import logging

# DB 마이그레이션용 SQL 직접 실행에 사용
from sqlalchemy import text

# FastAPI 기본 구성 요소들
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# 프로젝트에서 공통으로 쓰는 함수/설정들
from deps import (
    UPLOAD_DIR,       # 업로드 이미지가 저장되는 디렉터리 경로(Path)
    STATIC_DIR,       # CSS/JS 같은 정적 파일 디렉터리
    load_schedule,    # 일정 목록을 불러오는 함수
    load_todos,       # TODO 목록을 불러오는 함수
    schedule_sort_key,# 일정 정렬 기준 함수
    templates,        # Jinja2 템플릿 객체
    require_auth,     # 전역 Basic 인증(모든 요청에 적용)
)

# 각 기능별 라우터(일기, 일정, TODO, 통계, 백업/복원)
from routers import (
    diary_router,
    schedule_router,
    todos_router,
    stats_router,
    backup_router,
    restore_router,
)

# =========================
# DB 관련 (SQLAlchemy)
# =========================
from db import Base, engine
import models  # Diary / Schedule / Todo 모델 정의가 들어 있음

# 로깅용 로거 생성 (이 이름으로 로그를 남김)
logger = logging.getLogger("steplog")


# =========================
# 앱 & 공통 설정
# =========================

# FastAPI 애플리케이션 생성
# dependencies=[Depends(require_auth)] :
#   → 모든 엔드포인트에 require_auth가 자동으로 적용됨 (전역 Basic Auth)
app = FastAPI(
    dependencies=[Depends(require_auth)]
)

# 정적 파일(이미지, CSS 등) 제공 설정
# /uploads/ 경로로 들어온 요청은 UPLOAD_DIR 디렉터리에서 파일을 찾아서 응답
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
# /static/ 경로로 들어온 요청은 STATIC_DIR 디렉터리에서 파일을 제공
app.mount("/static",  StaticFiles(directory=STATIC_DIR),  name="static")

# 기능별 라우터 등록
# 각 라우터 안에 /diary, /schedule 같은 실제 엔드포인트들이 정의되어 있음
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
    """
    서버가 시작될 때 한 번만 실행되는 함수.

    1) SQLAlchemy 모델을 기반으로 DB 테이블이 없으면 생성
    2) todos 테이블에 sort_index 컬럼이 없으면 추가 (Postgres 기준)
    """
    logger.info(">>> STARTUP: creating DB tables via Base.metadata.create_all")

    # models 를 import 해서, Base에 모든 모델이 등록되도록 보장
    # (위에서 이미 import models를 했기 때문에 사실상 한 번 더 호출하는 셈이지만,
    #  import 는 한 번만 실제로 동작하고 이후에는 캐시를 사용하므로 성능 문제는 거의 없음)
    import models

    # Base 에 등록된 모든 모델을 기준으로 테이블 생성
    #   - 테이블이 이미 있으면 그대로 두고
    #   - 없으면 새로 만든다
    Base.metadata.create_all(bind=engine)

    # ---- 여기서부터 1회성 마이그레이션 ----
    # Postgres 의 todos 테이블에 sort_index 컬럼이 없으면 추가하는 SQL
    #   - Render(Postgres) 에서는 정상 동작
    #   - 로컬 SQLite 에서는 IF NOT EXISTS 문법 때문에 에러 로그가 찍히지만,
    #     아래 try/except 로 인해 앱 전체는 계속 실행된다.
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
        # 컬럼 추가에 실패해도 서버가 죽지 않도록 에러만 로그에 남긴다.
        logger.error(">>> STARTUP: failed to ensure todos.sort_index: %s", e)


# =========================
# 메인 대시보드 ("/")
# =========================
@app.get("/", response_class=HTMLResponse, name="home")
async def dashboard(request: Request):
    """
    메인 대시보드 페이지 핸들러.

    1) 오늘 날짜 기준으로
       - 향후 15일 이내 일정(upcoming)
       - 진행 중인 TODO 목록
       - 이번 달 달력 정보
      를 만들어서 dashboard.html 템플릿에 넘겨준다.
    """
    # 오늘 날짜 (date 객체)
    today = date.today()
    # "YYYY-MM-DD" 형태의 문자열로도 준비 (비교/템플릿용)
    today_str = today.isoformat()

    # ---- 일정 불러오기 ----
    schedule_items = load_schedule()

    # 오늘부터 15일 뒤까지를 보여줄 범위로 설정
    horizon = today + timedelta(days=15)

    # 오늘 ~ 15일 뒤까지의 일정만 필터링
    upcoming = [
        item for item in schedule_items
        if today_str <= item.date <= horizon.isoformat()
    ]

    # 정렬 기준 함수(schedule_sort_key)를 사용해서 일정 정렬
    upcoming_sorted = sorted(upcoming, key=schedule_sort_key)

    # ---- 오늘 TODO 목록 (진행 중인 것만) ----
    todos = load_todos()
    # status == "pending" 인 TODO만 오늘 보여준다
    today_todos = [t for t in todos if t.status == "pending"]

    # ---- 달력 데이터 생성 ----
    # firstweekday=6 → 일요일(6)부터 한 주를 시작하겠다는 의미
    cal = calendar.Calendar(firstweekday=6)
    weeks = []

    # monthdatescalendar(year, month):
    #   → 해당 월을 주(week) 단위로 끊어서, 각 주마다 7개의 date 객체 리스트를 반환
    for week in cal.monthdatescalendar(today.year, today.month):
        week_data = []
        for d in week:
            key = d.isoformat()
            week_data.append({
                "day": d.day,                          # 일(1~31)
                "in_month": (d.month == today.month),  # 이번 달에 속하는 날짜인지 여부
                "has_schedule": any(                   # 해당 날짜에 일정이 있는지 여부
                    it.date == key for it in schedule_items
                ),
                "is_today": (d == today),              # 오늘 날짜인지 여부
            })
        weeks.append(week_data)

    # === 수정: 아래 로그는 개발 중 디버깅용이라, 실제 서비스 운영에는 필수는 아님.
    # 필요할 때만 잠깐 주석을 풀어 사용해도 된다.
    # logger.info(
    #     "DASHBOARD_DEBUG: schedules_total=%d upcoming_shown=%d "
    #     "todos_total=%d pending_shown=%d",
    #     len(schedule_items),
    #     len(upcoming_sorted),
    #     len(todos),
    #     len(today_todos),
    # )

    # 템플릿에 데이터를 넘겨서 HTML을 렌더링
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


# 이 블록은 "python main.py" 로 직접 실행했을 때만 동작한다.
# Render 같은 환경에서는 보통 "uvicorn main:app" 명령으로 실행하므로,
# 여기 코드는 실행되지 않는다. (그래도 로컬 테스트용으로 남겨두는 것이 보통이다.)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
