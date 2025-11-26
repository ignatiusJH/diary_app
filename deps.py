# deps.py
from pathlib import Path
from datetime import datetime, date, timedelta
import json
import uuid
import math
import calendar
import os
import secrets
from typing import List

from fastapi import HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED
from pydantic import BaseModel

# =========================
# 공통 경로 / 상수
# =========================

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"   # 사진 저장
DATA_DIR   = BASE_DIR / "data"      # JSON 저장
STATIC_DIR = BASE_DIR / "static"    # 정적 파일 (이미지 등)

UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# 기록 목록 페이지당 개수
ITEMS_PER_PAGE_LIST    = 10
ITEMS_PER_PAGE_GALLERY = 50
HISTORY_ITEMS_PER_PAGE = 20  # 체크리스트 완료/포기 히스토리 1페이지당 개수

# JSON 파일 경로
SCHEDULE_FILE = DATA_DIR / "schedule.json"   # 일정
TODOS_FILE    = DATA_DIR / "todos.json"      # 체크리스트

# Jinja 템플릿
templates = Jinja2Templates(directory="templates")


# =========================
# 공통 유틸 (기록)
# =========================

def _normalize_entry(entry: dict) -> dict:
    """
    기록(JSON) 형식을 통일하는 함수
    - 줄바꿈 통일
    - 태그를 항상 리스트로 맞춰줌
    """
    content = entry.get("content") or ""
    if isinstance(content, str):
        entry["content"] = content.replace("\r\n", "\n")

    tags = entry.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    entry["tags"] = tags

    return entry


def _parse_tags(text: str) -> list[str]:
    """텍스트로 들어온 태그(쉼표 구분) → 리스트로 변환"""
    if not text:
        return []
    return [t.strip() for t in text.split(",") if t.strip()]


def load_entry(entry_id: str) -> dict:
    """단일 기록 1개 로드"""
    path = DATA_DIR / f"{entry_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Entry not found")

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    return _normalize_entry(data)


def save_entry_json(entry_id: str, entry: dict) -> None:
    """단일 기록 1개 저장"""
    path = DATA_DIR / f"{entry_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)


def delete_entry_json(entry_id: str) -> None:
    """단일 기록 1개 삭제 (파일 삭제)"""
    path = DATA_DIR / f"{entry_id}.json"
    if path.exists():
        path.unlink()


# =========================
# 일정 관련
# =========================

class ScheduleItem(BaseModel):
    id: str
    date: str           # "YYYY-MM-DD"
    title: str          # 일정 제목
    memo: str | None = None
    time: str | None = None      # "HH:MM" (선택)
    time_str: str | None = None  # 문자열용 (선택)
    place: str | None = None     # 장소 (선택)


def load_schedule() -> List[ScheduleItem]:
    """일정 전체 로드"""
    if not SCHEDULE_FILE.exists():
        return []

    with SCHEDULE_FILE.open("r", encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError:
            raw = []

    items: list[ScheduleItem] = []

    for item in raw:
        time_val = item.get("time")
        time_str_val = item.get("time_str")

        if time_val and not time_str_val:
            time_str_val = time_val
        if time_str_val and not time_val:
            time_val = time_str_val

        items.append(
            ScheduleItem(
                id=item.get("id", str(uuid.uuid4())),
                date=item.get("date", date.today().isoformat()),
                title=item.get("title", ""),
                memo=item.get("memo"),
                time=time_val,
                time_str=time_str_val,
                place=item.get("place"),
            )
        )

    save_schedule(items)
    return items


def schedule_sort_key(item: ScheduleItem):
    """
    일정 정렬 키:
    1) 날짜 오름차순
    2) 같은 날짜 안에서는 '시간 없음'이 먼저
    3) 그 다음 시간 오름차순
    """
    d = date.fromisoformat(item.date)
    t_str = (item.time_str or item.time or "").strip()

    if t_str:
        try:
            h, m = map(int, t_str.split(":"))
        except ValueError:
            h, m = 23, 59
        has_time = 1
    else:
        h, m = 0, 0
        has_time = 0

    return (d, has_time, h, m)


def save_schedule(items: List[ScheduleItem]) -> None:
    """일정 전체 저장"""
    data = [item.dict() for item in items]
    with SCHEDULE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# 체크리스트 관련
# =========================
# status 값은 항상 이 셋만 사용:
# - "pending" : 진행 중
# - "done"    : 완료
# - "giveup"  : 포기

class TodoItem(BaseModel):
    id: str
    date: str          # "YYYY-MM-DD"
    title: str
    status: str = "pending"  # "pending" / "done" / "giveup"


def load_todos() -> List[TodoItem]:
    """
    todos.json 을 읽어서 TodoItem 리스트로 반환.
    옛날 데이터(done: bool)도 자동으로 status 형식으로 변환한다.
    """
    if not TODOS_FILE.exists():
        return []

    with TODOS_FILE.open("r", encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError:
            raw = []

    normalized: list[TodoItem] = []

    for item in raw:
        todo_id = item.get("id", str(uuid.uuid4()))
        date_str = item.get("date", date.today().isoformat())
        title = item.get("title", "")

        if "status" in item:
            status = item["status"]
        else:
            done_flag = item.get("done", False)
            status = "done" if done_flag else "pending"

        if status not in ("pending", "done", "giveup"):
            status = "pending"

        normalized.append(
            TodoItem(
                id=todo_id,
                date=date_str,
                title=title,
                status=status,
            )
        )

    save_todos(normalized)
    return normalized


def save_todos(items: List[TodoItem]) -> None:
    """TodoItem 리스트를 todos.json 에 저장."""
    data = [item.dict() for item in items]
    with TODOS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# 접속 제한(나만 보기)용 의존성
# =========================

security = HTTPBasic()


def owner_only(credentials: HTTPBasicCredentials = Depends(security)):
    """
    HTTP Basic Auth 로 '주인만 접속'하게 막는 의존성.

    환경변수:
      STEPLOG_USER  : 아이디 (기본값: owner)
      STEPLOG_PASS  : 비밀번호 (기본값: change-me)
    """
    username = os.getenv("STEPLOG_USER", "owner")
    password = os.getenv("STEPLOG_PASS", "change-me")

    ok_user = secrets.compare_digest(credentials.username, username)
    ok_pass = secrets.compare_digest(credentials.password, password)

    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Not authorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True
