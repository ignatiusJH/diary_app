# routers/todos.py
from datetime import date
from typing import List

from fastapi import APIRouter, Request, Form, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from deps import (
    HISTORY_ITEMS_PER_PAGE,
    templates,
)
from db import get_db
from models import Todo

router = APIRouter()


# -----------------------------
# 헬퍼: Todo 모델 → 템플릿에서 쓰기 편한 형태
# -----------------------------
def _todo_to_dict(row: Todo) -> dict:
    return {
        "id": row.id,
        "date": row.date,
        "title": row.title,
        "status": row.status,
        "order": row.order,
    }


# =========================
# 1) 메인 To-do 페이지
# =========================
@router.get("/todos", response_class=HTMLResponse, name="todo_page")
async def todo_page(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    history_status: str = "all",
    history_page: int = 1,
    open_history: int = 0,
    db: Session = Depends(get_db),
):
    # ----- 전체에서 pending / history 분리 -----
    pending_query = (
        db.query(Todo)
        .filter(Todo.status == "pending")
        .order_by(Todo.order.asc(), Todo.date.asc())
    )
    pending_rows = pending_query.all()
    pending_items = [_todo_to_dict(r) for r in pending_rows]
    visible_items = pending_items

    history_query = db.query(Todo).filter(Todo.status.in_(["done", "giveup"]))

    # 날짜 필터
    start_date = None
    end_date = None

    if start:
        try:
            start_date = date.fromisoformat(start)
            history_query = history_query.filter(Todo.date >= start_date.isoformat())
        except ValueError:
            start_date = None

    if end:
        try:
            end_date = date.fromisoformat(end)
            history_query = history_query.filter(Todo.date <= end_date.isoformat())
        except ValueError:
            end_date = None

    # 상태 필터
    status_key = history_status or "all"
    if status_key == "done":
        history_query = history_query.filter(Todo.status == "done")
    elif status_key == "giveup":
        history_query = history_query.filter(Todo.status == "giveup")

    # 정렬 (날짜, id 역순)
    history_query = history_query.order_by(Todo.date.desc(), Todo.id.desc())

    # 페이지네이션
    per_page = HISTORY_ITEMS_PER_PAGE
    total_history = history_query.count()

    if total_history > 0:
        total_pages = max(1, (total_history + per_page - 1) // per_page)
    else:
        total_pages = 1

    page = max(1, min(history_page, total_pages))

    history_rows = (
        history_query
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    history_page_items = [_todo_to_dict(r) for r in history_rows]

    history_open = bool(open_history)

    return templates.TemplateResponse(
        "todos.html",
        {
            "request": request,
            "items": visible_items,
            "history_items": history_page_items,
            "history_start": start,
            "history_end": end,
            "history_status": status_key,
            "history_page": page,
            "history_total_pages": total_pages,
            "history_open": history_open,
        },
    )


# =========================
# 2) To-do 생성
# =========================
@router.post("/todos", response_class=RedirectResponse)
async def create_todo(
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    # 새 pending 중 가장 큰 order + 1 로 설정
    max_order = (
        db.query(func.max(Todo.order))
        .filter(Todo.status == "pending")
        .scalar()
    )
    next_order = (max_order or 0) + 1

    new_item = Todo(
        id=str(__import__("uuid").uuid4()),
        date=date.today().isoformat(),
        title=title,
        status="pending",
        order=next_order,
    )
    db.add(new_item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================
# 3) 제목 수정
# =========================
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
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    item.title = title
    db.add(item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================
# 4) 완료 처리
# =========================
@router.post("/todos/{todo_id}/done", response_class=RedirectResponse)
async def mark_todo_done(
    todo_id: str,
    db: Session = Depends(get_db),
):
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    item.status = "done"
    db.add(item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================
# 5) 포기 처리
# =========================
@router.post("/todos/{todo_id}/giveup", response_class=RedirectResponse)
async def mark_todo_giveup(
    todo_id: str,
    db: Session = Depends(get_db),
):
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    item.status = "giveup"
    db.add(item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================
# 6) 삭제
# =========================
@router.post(
    "/todos/{todo_id}/delete",
    response_class=RedirectResponse,
    name="delete_todo",
)
async def delete_todo(
    todo_id: str,
    db: Session = Depends(get_db),
):
    item = db.get(Todo, todo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")

    db.delete(item)
    db.commit()

    return RedirectResponse(url="/todos", status_code=303)


# =========================
# 7) 순서 변경 (드래그 정렬)
# =========================
@router.post("/todos/reorder")
async def reorder_todos(
    order: List[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """
    pending 상태의 투두들에 대해서만 순서(order)를 재설정.
    order 리스트에 없는 id 는 맨 뒤로 보낸다.
    """
    order_map = {tid: idx for idx, tid in enumerate(order)}

    pending_items = (
        db.query(Todo)
        .filter(Todo.status == "pending")
        .all()
    )

    for item in pending_items:
        item.order = order_map.get(item.id, 10_000_000)
        db.add(item)

    db.commit()

    return {"status": "ok"}
