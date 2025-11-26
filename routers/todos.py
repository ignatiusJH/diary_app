# routers/todos.py
from datetime import date
from typing import List

from fastapi import APIRouter, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse

from deps import (
    TodoItem,
    load_todos,
    save_todos,
    HISTORY_ITEMS_PER_PAGE,
    templates,
)

router = APIRouter()


@router.get("/todos", response_class=HTMLResponse, name="todo_page")
async def todo_page(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    history_status: str = "all",
    history_page: int = 1,
    open_history: int = 0,
):
    items = load_todos()

    pending_items = [it for it in items if it.status == "pending"]
    visible_items = pending_items

    history = [it for it in items if it.status in ("done", "giveup")]

    start_date: date | None = None
    end_date:   date | None = None

    if start:
        try:
            start_date = date.fromisoformat(start)
        except ValueError:
            start_date = None

    if end:
        try:
            end_date = date.fromisoformat(end)
        except ValueError:
            end_date = None

    if start_date or end_date:
        def in_range(it: TodoItem) -> bool:
            try:
                d = date.fromisoformat(it.date)
            except ValueError:
                return True
            if start_date and d < start_date:
                return False
            if end_date and d > end_date:
                return False
            return True

        history = [it for it in history if in_range(it)]

    status_key = history_status or "all"
    if status_key == "done":
        history = [it for it in history if it.status == "done"]
    elif status_key == "giveup":
        history = [it for it in history if it.status == "giveup"]

    history_sorted = sorted(
        history,
        key=lambda it: (it.date, it.id),
        reverse=True,
    )

    total_history = len(history_sorted)
    per_page = HISTORY_ITEMS_PER_PAGE

    if total_history > 0:
        total_pages = max(1, (total_history + per_page - 1) // per_page)
    else:
        total_pages = 1

    page = max(1, min(history_page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx   = start_idx + per_page
    history_page_items = history_sorted[start_idx:end_idx]

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


@router.post("/todos", response_class=RedirectResponse)
async def create_todo(
    title: str = Form(...),
):
    items = load_todos()
    new_item = TodoItem(
        id=str(__import__("uuid").uuid4()),
        date=date.today().isoformat(),
        title=title,
        status="pending",
    )
    items.append(new_item)
    save_todos(items)
    return RedirectResponse(url="/todos", status_code=303)


@router.post(
    "/todos/{todo_id}/update",
    response_class=RedirectResponse,
    name="update_todo",
)
async def update_todo(
    todo_id: str,
    title: str = Form(...),
):
    items = load_todos()
    for item in items:
        if item.id == todo_id:
            item.title = title
            break
    save_todos(items)
    return RedirectResponse(url="/todos", status_code=303)


@router.post("/todos/{todo_id}/done", response_class=RedirectResponse)
async def mark_todo_done(todo_id: str):
    items = load_todos()
    for item in items:
        if item.id == todo_id:
            item.status = "done"
            break
    save_todos(items)
    return RedirectResponse(url="/todos", status_code=303)


@router.post("/todos/{todo_id}/giveup", response_class=RedirectResponse)
async def mark_todo_giveup(todo_id: str):
    items = load_todos()
    for item in items:
        if item.id == todo_id:
            item.status = "giveup"
            break
    save_todos(items)
    return RedirectResponse(url="/todos", status_code=303)


@router.post(
    "/todos/{todo_id}/delete",
    response_class=RedirectResponse,
    name="delete_todo",
)
async def delete_todo(todo_id: str):
    items = load_todos()
    items = [item for item in items if item.id != todo_id]
    save_todos(items)
    return RedirectResponse(url="/todos", status_code=303)


@router.post("/todos/reorder")
async def reorder_todos(order: List[str] = Body(..., embed=True)):
    items = load_todos()
    order_map = {tid: idx for idx, tid in enumerate(order)}

    pending = [it for it in items if it.status == "pending"]
    others  = [it for it in items if it.status != "pending"]

    pending_sorted = sorted(
        pending,
        key=lambda it: order_map.get(it.id, 10_000_000),
    )

    new_items = pending_sorted + others
    save_todos(new_items)

    return {"status": "ok"}
