# routers/schedule.py
# ---------------------------------------------------------
# 일정(Schedule) 기능을 담당하는 라우터.
#
# 기능 목록:
#   1) 일정 목록 화면 (/schedule)
#   2) 일정 생성 폼 (/schedule/new)
#   3) 일정 생성 처리
#   4) 일정 수정 처리
#   5) 일정 삭제
#   6) JSON API (인라인 에디터용)
#
# 모든 일정 데이터는 SQLAlchemy의 Schedule 모델을 사용한다.
# /schedule 화면에서는 기본적으로 "오늘 이후" 일정만 보여준다.
# ---------------------------------------------------------

from datetime import date
from typing import Optional

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from deps import templates  # Jinja 템플릿 엔진
from db import get_db
from models import Schedule

# 이 파일에서 사용할 라우터 생성
router = APIRouter()


# ---------------------------------------------------------
# 헬퍼 함수: Schedule ORM → 템플릿/JSON에서 쓰기 좋은 dict
# ---------------------------------------------------------
def _schedule_to_dict(row: Schedule) -> dict:
    """
    ORM 모델 Schedule 객체를 템플릿 또는 JSON API에서 쓰기 편한 dict 구조로 변환한다.
    """
    return {
        "id": str(row.id),
        "date": row.date,         # "YYYY-MM-DD"
        "title": row.title,
        "memo": row.memo,
        "time": row.time_str,     # 예전 코드 호환을 위해 time 키도 유지
        "time_str": row.time_str, # 실제 사용하는 시간 문자열
        "place": row.place,
        "done": row.done,
    }


# =========================================================
# 1) 일정 목록 화면
# =========================================================
@router.get("/schedule", response_class=HTMLResponse, name="schedule_page")
async def schedule_page(
    request: Request,
    start: Optional[str] = None,   # 필터 시작일(옵션)
    end: Optional[str] = None,     # 필터 종료일(옵션)
    db: Session = Depends(get_db),
):
    """
    일정 목록 화면.

    ✔ 기본 로직:
       - '오늘 날짜 이상'인 일정만 보여준다. (과거 일정은 목록에서 제외)
    ✔ start, end 쿼리 파라미터가 있으면 해당 기간으로 필터링한다.
    """
    today = date.today()
    today_str = today.isoformat()

    # 모든 일정 SELECT
    query = db.query(Schedule)

    # -----------------------------
    # 기본: 오늘 이후 일정만
    # -----------------------------
    query = query.filter(Schedule.date >= today_str)

    # -----------------------------
    # start 파라미터로 기간 필터링
    # -----------------------------
    if start:
        try:
            start_date = date.fromisoformat(start)
            query = query.filter(Schedule.date >= start_date.isoformat())
        except ValueError:
            # 잘못된 날짜 형식이면 필터링 안 함
            start_date = None
    else:
        start_date = None

    # -----------------------------
    # end 파라미터로 기간 필터링
    # -----------------------------
    if end:
        try:
            end_date = date.fromisoformat(end)
            query = query.filter(Schedule.date <= end_date.isoformat())
        except ValueError:
            end_date = None
    else:
        end_date = None

    # 날짜 → 제목 순 정렬
    rows = (
        query
        .order_by(Schedule.date.asc(), Schedule.title.asc())
        .all()
    )

    items = [_schedule_to_dict(r) for r in rows]

    # 화면 렌더링
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


# =========================================================
# 2) 일정 생성 폼
# =========================================================
@router.get("/schedule/new", response_class=HTMLResponse, name="new_schedule_form")
async def new_schedule_form(request: Request):
    """
    일정 생성 폼 보여주는 페이지.
    기본 날짜는 '오늘 날짜'.
    """
    today_str = date.today().isoformat()
    return templates.TemplateResponse(
        "schedule_form.html",
        {
            "request": request,
            "default_date": today_str,
        },
    )


# =========================================================
# 3) 일정 생성 처리 (POST)
# =========================================================
@router.post("/schedule/new")
async def create_schedule(
    request: Request,
    date_str: str = Form(...),     # 날짜 (필수)
    title: str = Form(...),        # 제목 (필수)
    memo: str = Form(""),          # 메모 (선택값)
    time_str: str = Form(""),      # 시간 (선택값)
    place: str = Form(""),         # 장소 (선택값)
    db: Session = Depends(get_db),
):
    """
    일정 생성 처리.
    - 폼에서 받은 값을 Schedule 모델로 만들어 DB에 INSERT 한다.
    """
    item = Schedule(
        date=date_str,
        title=title,
        memo=memo or None,          # 빈 문자열이면 None 저장
        time_str=time_str or None,
        place=place or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)  # INSERT 후 생성된 PK(id) 반영

    return RedirectResponse(url="/schedule", status_code=303)


# =========================================================
# 4) 일정 수정 처리 (POST)
# =========================================================
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
    """
    일정 수정 처리.
    - 기존 Schedule 객체를 가져와서 필드를 업데이트한다.
    """
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


# =========================================================
# 5) 일정 삭제
# =========================================================
@router.post("/schedule/{schedule_id}/delete", response_class=RedirectResponse)
async def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
):
    """
    일정 삭제.
    """
    item = db.get(Schedule, int(schedule_id))
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(item)
    db.commit()

    return RedirectResponse(url="/schedule", status_code=303)


# =========================================================
# 6) 일정 JSON API (인라인 에디터용)
# =========================================================
@router.get("/api/schedule/{schedule_id}")
async def api_get_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
):
    """
    일정 탭 오른쪽 인라인 에디터용 JSON 데이터 반환 API.
    - 프론트엔드에서 fetch로 호출해서 JSON 데이터를 가져감.
    """
    item = db.get(Schedule, int(schedule_id))
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return _schedule_to_dict(item)
