# routers/todos.py
# =========================================================
# 체크리스트(Todo) 기능 라우터
#
# 상태 값:
#   - "pending" : 진행 중
#   - "done"    : 완료
#   - "giveup"  : 포기
#
# 주요 기능:
#   1) /todos 메인 페이지 (진행 중 + 완료/포기 히스토리)
#   2) Todo 생성
#   3) 제목 수정
#   4) 완료 처리
#   5) 포기 처리
#   6) 삭제 (진행 중 / 히스토리 모두 공용)
#   7) 드래그로 순서 변경 (pending 전용)
#
# UX 포인트:
#   - 완료/포기 히스토리 카드는 접었다/펼칠 수 있음
#   - 히스토리 안에서 삭제했을 때도,
#     다시 /todos 로 돌아가면 패널이 열린 상태(open_history=1)로 유지되도록 처리
# =========================================================

from datetime import date
from typing import List

from fastapi import APIRouter, Request, Form, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from deps import (
    HISTORY_ITEMS_PER_PAGE,  # 히스토리(완료/포기) 페이지당 개수
    templates,
)
from db import get_db
from models import Todo

router = APIRouter()


# ---------------------------------------------------------
# 헬퍼 함수: Todo ORM → dict
# ---------------------------------------------------------
def _todo_to_dict(row: Todo) -> dict:
    """
    SQLAlchemy Todo 객체를 템플릿/JSON에서 사용하기 쉬운 dict 형태로 변환.

    템플릿에서:
      - {{ item.id }}
      - {{ item.date }}
      - {{ item.title }}
      - {{ item.status }}
      - {{ item.order }}
    이런 식으로 바로 접근할 수 있게 하기 위한 헬퍼.
    """
    return {
        "id": row.id,
        "date": row.date,       # "YYYY-MM-DD"
        "title": row.title,
        "status": row.status,   # "pending" / "done" / "giveup"
        "order": row.order,     # 정렬용 인덱스
    }


# =========================================================
# 1) 메인 To-do 페이지
# =========================================================
@router.get("/todos", response_class=HTMLResponse, name="todo_page")
async def todo_page(
    request: Request,
    start: str | None = None,          # 히스토리 시작 날짜 필터 (YYYY-MM-DD)
    end: str | None = None,            # 히스토리 종료 날짜 필터 (YYYY-MM-DD)
    history_status: str = "all",       # all / done / giveup
    history_page: int = 1,             # 히스토리 페이지 번호 (1부터 시작)
    open_history: int = 0,             # 히스토리 영역 열기 여부(0/1) - JS에서는 URL 파라미터로 사용
    db: Session = Depends(get_db),
):
    """
    메인 체크리스트 페이지.

    화면 구성:
      - 오른쪽(또는 상단): 진행 중(pending) 목록
      - 왼쪽(또는 하단): 완료/포기 히스토리 (접었다/펼칠 수 있음)

    URL 예시:
      - /todos                           → 기본 (히스토리 닫힘)
      - /todos?open_history=1           → 히스토리 패널 열린 상태
      - /todos?start=2025-01-01&end=... → 기간 필터 적용
    """

    # -----------------------------------------------------
    # 1) 진행 중(pending) 목록 조회
    # -----------------------------------------------------
    pending_query = (
        db.query(Todo)
        .filter(Todo.status == "pending")
        .order_by(Todo.order.asc(), Todo.date.asc())
    )
    pending_rows = pending_query.all()
    pending_items = [_todo_to_dict(r) for r in pending_rows]

    # 현재 화면에서 보여줄 메인 리스트
    visible_items = pending_items

    # -----------------------------------------------------
    # 2) 완료/포기 히스토리 조회 쿼리 구성
    # -----------------------------------------------------
    history_query = db.query(Todo).filter(Todo.status.in_(["done", "giveup"]))

    # 날짜 필터용 변수 (템플릿에서도 그대로 보여줄 수 있도록 저장)
    start_date = None
    end_date = None

    # 시작일 필터
    if start:
        try:
            start_date = date.fromisoformat(start)
            # date 칼럼이 문자열(YYYY-MM-DD)이라면 isoformat()과 비교해도 무방
            history_query = history_query.filter(Todo.date >= start_date.isoformat())
        except ValueError:
            # 잘못된 날짜 형식이면 필터를 적용하지 않고 무시
            start_date = None

    # 종료일 필터
    if end:
        try:
            end_date = date.fromisoformat(end)
            history_query = history_query.filter(Todo.date <= end_date.isoformat())
        except ValueError:
            end_date = None

    # 상태 필터 (all / done / giveup)
    status_key = history_status or "all"
    if status_key == "done":
        history_query = history_query.filter(Todo.status == "done")
    elif status_key == "giveup":
        history_query = history_query.filter(Todo.status == "giveup")

    # 날짜 내림차순, id 내림차순 (가장 최근 것이 위로 오도록)
    history_query = history_query.order_by(Todo.date.desc(), Todo.id.desc())

    # -----------------------------------------------------
    # 3) 히스토리 페이징 처리
    # -----------------------------------------------------
    per_page = HISTORY_ITEMS_PER_PAGE
    total_history = history_query.count()

    if total_history > 0:
        # 올림 나눗셈: (total + per_page - 1) // per_page
        total_pages = max(1, (total_history + per_page - 1) // per_page)
    else:
        total_pages = 1

    # 요청된 페이지 번호를 1~total_pages 범위로 보정
    page = max(1, min(history_page, total_pages))

    history_rows = (
        history_query
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    history_page_items = [_todo_to_dict(r) for r in history_rows]

    # open_history(0/1) → bool 로 변환 (템플릿에서 필요하면 사용)
    history_open = bool(open_history)

    # -----------------------------------------------------
    # 4) 템플릿 렌더링
    # -----------------------------------------------------
    return templates.TemplateResponse(
        "todos.html",
        {
            "request": request,
            "items": visible_items,                 # 진행 중 목록
            "history_items": history_page_items,    # 히스토리 페이지 데이터
            "history_start": start,                 # 기간 필터 시작값 (문자열 그대로)
            "history_end": end,                     # 기간 필터 종료값
            "history_status": status_key,           # 현재 선택된 상태 필터
            "history_page": page,                   # 현재 히스토리 페이지
            "history_total_pages": total_pages,     # 히스토리 전체 페이지 수
            "history_open": history_open,           # 서버 기준 open 여부 (JS는 URL 파라미터를 사용)
        },
    )


# =========================================================
# 2) To-do 생성
# =========================================================
@router.post("/todos", response_class=RedirectResponse)
async def create_todo(
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    새로운 Todo 생성.

    규칙:
      - 항상 "오늘 날짜(date.today())"로 생성
      - status = "pending"
      - order = 현재 pending 중 가장 큰 값 + 1
    """
    # pending 상태에서 가장 큰 order 값 조회
    max_order = (
        db.query(func.max(Todo.order))
        .filter(Todo.status == "pending")
        .scalar()
    )
    next_order = (max_order or 0) + 1

    # uuid 문자열로 id 생성
    new_item = Todo(
        id=str(__import__("uuid").uuid4()),
        date=date.today().isoformat(),
        title=title,
        status="pending",
        order=next_order,
    )
    db.add(new_item)
    db.commit()

    # 303 See Other: POST 이후 GET /todos 로 리다이렉트
    return RedirectResponse(url="/todos", status_code=303)


# =========================================================
# 3) 제목 수정
# =========================================================
@router.post(
    "/todos/{todo_id}/update",
    response_class=RedirectResponse,
    name="update_todo",
)
async def update_todo(
    todo_id: str,
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Todo 제목 수정.
    - 주로 진행 중(pending) 리스트에서 인라인 수정에 사용.
    """
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    item.title = title
    db.add(item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================================================
# 4) 완료 처리
# =========================================================
@router.post("/todos/{todo_id}/done", response_class=RedirectResponse)
async def mark_todo_done(
    todo_id: str,
    db: Session = Depends(get_db),
):
    """
    Todo를 '완료(done)' 상태로 변경.
    - pending → done 으로 상태만 바꿔준다.
    """
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    item.status = "done"
    db.add(item)
    db.commit()

    # 완료 처리 후에는 기본 /todos 로 돌아가고,
    # 히스토리는 필요하면 사용자가 "열기"로 확인.
    return RedirectResponse(url="/todos", status_code=303)


# =========================================================
# 5) 포기 처리
# =========================================================
@router.post("/todos/{todo_id}/giveup", response_class=RedirectResponse)
async def mark_todo_giveup(
    todo_id: str,
    db: Session = Depends(get_db),
):
    """
    Todo를 '포기(giveup)' 상태로 변경.
    - pending → giveup 으로 상태만 바꿔준다.
    """
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    item.status = "giveup"
    db.add(item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================================================
# 6) 삭제 (진행 중 / 히스토리 공용)
# =========================================================
@router.post(
    "/todos/{todo_id}/delete",
    response_class=RedirectResponse,
    name="delete_todo",
)
async def delete_todo(
    todo_id: str,
    db: Session = Depends(get_db),
):
    """
    Todo 한 개 삭제.

    사용 위치:
      - 진행 중 리스트(pending)에서 삭제
      - 완료/포기 히스토리 카드에서 삭제 (같은 엔드포인트 재사용)

    UX:
      - 히스토리 패널에서 삭제한 뒤에도 패널이 접히지 않도록,
        항상 /todos?open_history=1 로 리다이렉트한다.
        (진행 중에서 삭제해도 동일한 URL로 가지만 문제 없음)
    """
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    db.delete(item)
    db.commit()

    # 히스토리 패널을 계속 열린 상태로 유지하고 싶으므로
    # open_history=1 을 URL에 붙여서 리다이렉트한다.
    return RedirectResponse(url="/todos?open_history=1", status_code=303)


# =========================================================
# 7) 순서 변경 (드래그 정렬용)
# =========================================================
@router.post("/todos/reorder")
async def reorder_todos(
    order: List[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """
    드래그&드롭으로 변경된 순서를 반영하는 API.

    대상:
      - status = "pending" 인 Todo 들만 정렬 대상.

    파라미터:
      - order: ["id1", "id2", "id3", ...]
        * 앞에 있을수록 우선순위가 높다.
        * 리스트에 없는 id들은 '맨 뒤'로 밀려난다.

    로직:
      1) order 리스트에서 id → index 매핑을 만든다.
      2) pending Todo 들을 돌면서:
         - 리스트 안에 있으면 해당 index 로 order 값을 설정
         - 리스트에 없으면 10_000_000 같은 아주 큰 숫자로 설정 (맨 뒤)
    """
    # id → 새 order 인덱스 매핑
    order_map = {tid: idx for idx, tid in enumerate(order)}

    pending_items = (
        db.query(Todo)
        .filter(Todo.status == "pending")
        .all()
    )

    for item in pending_items:
        # 리스트에 있으면 해당 인덱스, 없으면 매우 큰 번호로 보내기
        item.order = order_map.get(item.id, 10_000_000)
        db.add(item)

    db.commit()

    return {"status": "ok"}
