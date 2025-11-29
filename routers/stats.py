# routers/stats.py
# -----------------------------------------------
# 체크리스트(Todo) 데이터를 기반으로 통계를 계산하고,
# stats.html 템플릿에 넘겨주는 라우터.
#
# 핵심 기능:
#   1) 전체 기간 통계 계산
#   2) 선택된 기간(start~end) 통계 계산
#   3) 날짜 필터링(start, end)
#   4) 템플릿 렌더링
#
# 주의할 점:
#   - Todo.date 는 문자열("YYYY-MM-DD")로 저장되어 있으므로
#     비교하려면 date 객체로 변환해서 처리해야 한다.
#   - 파라미터 start/end 가 없으면 전체 기간을 사용한다.
# -----------------------------------------------

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
    start: str | None = None,   # 쿼리로 들어오는 시작 날짜 (YYYY-MM-DD)
    end: str | None = None,     # 쿼리로 들어오는 종료 날짜
    db: Session = Depends(get_db),
):
    """
    상태/통계 페이지 라우터.

    - start/end 쿼리를 기준으로 기간별 통계를 계산한다.
    - 아무 값도 없으면 전체 기록을 대상으로 한다.
    - 템플릿(stats.html)로 통계를 넘겨준다.
    """

    # --------------------------------------------------------
    # 1) 전체 Todo 데이터를 전부 가져오기
    # --------------------------------------------------------
    rows = (
        db.query(Todo)
        .order_by(Todo.date.asc())  # 날짜 오름차순 정렬
        .all()
    )

    # 데이터가 하나도 없으면 0으로 가득찬 화면 렌더링
    if not rows:
        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                # 전체 기간
                "overall_total": 0,
                "overall_done": 0,
                "overall_giveup": 0,
                "overall_pending": 0,
                "overall_done_rate": 0.0,
                "overall_gaveup_rate": 0.0,
                # 선택 기간
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

    # rows -> Todo 객체 리스트
    items = rows

    # --------------------------------------------------------
    # 2) 전체 기간 통계 계산
    # --------------------------------------------------------

    # 전체 항목 수
    overall_total = len(items)

    # 상태별 개수 계산
    overall_done    = sum(1 for it in items if it.status == "done")
    overall_giveup  = sum(1 for it in items if it.status == "giveup")
    overall_pending = sum(1 for it in items if it.status == "pending")

    # 비율 계산 (0 으로 나누는 것 방지)
    if overall_total > 0:
        overall_done_rate   = round(overall_done / overall_total * 100, 1)
        overall_gaveup_rate = round(overall_giveup / overall_total * 100, 1)
    else:
        overall_done_rate = overall_gaveup_rate = 0.0

    # --------------------------------------------------------
    # 3) 전체 Todo 데이터의 날짜 범위 구하기
    #    → 선택 기간을 지정하지 않으면 이 값을 기본값으로 사용
    #
    # Todo.date 는 문자열이므로 date 객체로 변환해서 판단해야 한다.
    # --------------------------------------------------------

    # 모든 Todo.date 값을 set → sorted → 첫날/마지막날 추출
    all_dates = sorted({it.date for it in items})

    # 데이터가 존재하니까 all_dates[0]과 [-1]은 항상 존재
    default_start = date.fromisoformat(all_dates[0])
    default_end   = date.fromisoformat(all_dates[-1])

    # 쿼리(start, end)가 있다면 변환하고,
    # 없다면 default 사용
    if start:
        start_date = date.fromisoformat(start)
    else:
        start_date = default_start

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = default_end

    # --------------------------------------------------------
    # 4) 선택 기간(start_date~end_date) 통계 계산
    #    - Todo.date 문자열을 date로 변환 후 범위 체크
    # --------------------------------------------------------

    def in_range(it: Todo) -> bool:
        """
        이 Todo 가 선택된 기간 안에 포함되는지 판단.
        """
        d = date.fromisoformat(it.date)
        return (d >= start_date) and (d <= end_date)

    # 선택 기간에 해당하는 Todo 객체들만 필터링
    ranged = [it for it in items if in_range(it)]

    # 기간 내 개수
    range_total   = len(ranged)
    range_done    = sum(1 for it in ranged if it.status == "done")
    range_giveup  = sum(1 for it in ranged if it.status == "giveup")
    range_pending = sum(1 for it in ranged if it.status == "pending")

    if range_total > 0:
        range_done_rate   = round(range_done / range_total * 100, 1)
        range_gaveup_rate = round(range_giveup / range_total * 100, 1)
    else:
        range_done_rate = range_gaveup_rate = 0.0

    # --------------------------------------------------------
    # 5) 템플릿 렌더링(stats.html)
    # --------------------------------------------------------
    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,

            # 전체 기간 통계
            "overall_total": overall_total,
            "overall_done": overall_done,
            "overall_giveup": overall_giveup,
            "overall_pending": overall_pending,
            "overall_done_rate": overall_done_rate,
            "overall_gaveup_rate": overall_gaveup_rate,

            # 선택한 기간(start~end) 정보
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),

            # 선택 기간 내 통계
            "range_total": range_total,
            "range_done": range_done,
            "range_giveup": range_giveup,
            "range_pending": range_pending,
            "range_done_rate": range_done_rate,
            "range_gaveup_rate": range_gaveup_rate,
        },
    )
