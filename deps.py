# deps.py
from pathlib import Path
from datetime import datetime, date, timedelta
import json
import uuid
import math
import calendar
import os
import secrets
import sqlite3
from typing import List

from fastapi import HTTPException, Depends, status
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED
from pydantic import BaseModel
from dotenv import load_dotenv

# =========================
# 공통 경로 / 상수
# =========================

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"   # 사진 저장
DATA_DIR   = BASE_DIR / "data"      # 데이터 저장
STATIC_DIR = BASE_DIR / "static"    # 정적 파일 (이미지 등)

UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# SQLite DB 경로
DB_PATH = DATA_DIR / "steplog.db"

# 기록 목록 페이지당 개수
ITEMS_PER_PAGE_LIST    = 10
ITEMS_PER_PAGE_GALLERY = 50
HISTORY_ITEMS_PER_PAGE = 20  # 체크리스트 완료/포기 히스토리 1페이지당 개수

# JSON 파일 경로 (이제 사용 안 하지만, 혹시 모를 마이그레이션용으로 남겨둠)
SCHEDULE_FILE = DATA_DIR / "schedule.json"   # 일정
TODOS_FILE    = DATA_DIR / "todos.json"      # 체크리스트

# .env 로드
load_dotenv()

# HTTP Basic 설정
security = HTTPBasic()

# Jinja 템플릿
templates = Jinja2Templates(directory="templates")


# =========================
# DB 유틸
# =========================

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """앱 시작 시 한 번만 호출: 필요한 테이블 생성."""
    with get_connection() as conn:
        cur = conn.cursor()

        # 일기 테이블
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS diary_entries (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                image_url  TEXT,
                created_at TEXT,
                updated_at TEXT,
                tags       TEXT   -- JSON 문자열
            )
            """
        )

        # 일정 테이블
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_items (
                id       TEXT PRIMARY KEY,
                date     TEXT NOT NULL,   -- YYYY-MM-DD
                title    TEXT NOT NULL,
                memo     TEXT,
                time     TEXT,            -- HH:MM
                time_str TEXT,
                place    TEXT
            )
            """
        )

        # 체크리스트 테이블
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id     TEXT PRIMARY KEY,
                date   TEXT NOT NULL,   -- YYYY-MM-DD
                title  TEXT NOT NULL,
                status TEXT NOT NULL    -- pending / done / giveup
            )
            """
        )

        conn.commit()


# 모듈 임포트 시 DB 초기화
init_db()


# =========================
# 인증
# =========================

def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """
    전체 앱에 공통으로 걸 인증 의존성.
    브라우저에서 아이디/비번을 물어보는 Basic Auth 방식.
    """
    correct_user = os.getenv("DIARY_USER")
    correct_pass = os.getenv("DIARY_PASSWORD")

    # 환경변수 안 넣으면 개발 중에 헷갈릴 수 있으니까 예외 던져버리기
    if not correct_user or not correct_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth env vars (DIARY_USER / DIARY_PASSWORD) are not set.",
        )

    if credentials.username != correct_user or credentials.password != correct_pass:
        # 잘못된 인증 → 401 + WWW-Authenticate 헤더
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # 여기까지 통과하면 인증 성공
    return credentials.username


# =========================
# 공통 유틸 (기록)
# =========================

def _normalize_entry(entry: dict) -> dict:
    """
    기록 형식을 통일하는 함수
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


# =========================
# 일기(기록) 관련: SQLite 버전
# =========================

def _decode_tags(tags_raw: str | None) -> list[str]:
    if not tags_raw:
        return []
    try:
        return json.loads(tags_raw)
    except json.JSONDecodeError:
        # 예전 형식이거나 그냥 문자열일 경우
        return _parse_tags(tags_raw)


def load_entry(entry_id: str) -> dict:
    """단일 기록 1개 로드 (SQLite)"""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, title, content, image_url, created_at, updated_at, tags
            FROM diary_entries
            WHERE id = ?
            """,
            (entry_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = dict(row)
    entry["tags"] = _decode_tags(entry.get("tags"))
    entry = _normalize_entry(entry)
    return entry


def save_entry_json(entry_id: str, entry: dict) -> None:
    """
    단일 기록 1개 저장 (이전 함수 이름 유지)
    - 없으면 INSERT
    - 있으면 UPDATE
    """
    entry = _normalize_entry(entry.copy())
    tags = entry.get("tags") or []
    tags_json = json.dumps(tags, ensure_ascii=False)

    title = entry.get("title", "")
    content = entry.get("content", "")
    image_url = entry.get("image_url")
    created_at = entry.get("created_at")
    updated_at = entry.get("updated_at")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO diary_entries (id, title, content, image_url, created_at, updated_at, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title      = excluded.title,
                content    = excluded.content,
                image_url  = excluded.image_url,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                tags       = excluded.tags
            """,
            (entry_id, title, content, image_url, created_at, updated_at, tags_json),
        )
        conn.commit()


def delete_entry_json(entry_id: str) -> None:
    """단일 기록 1개 삭제 (SQLite)"""
    with get_connection() as conn:
        conn.execute("DELETE FROM diary_entries WHERE id = ?", (entry_id,))
        conn.commit()


def load_all_entries() -> list[dict]:
    """
    전체 기록 목록 로드 (최신순).
    - diary_index 에서 목록 + 검색용으로 사용.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, title, content, image_url, created_at, updated_at, tags
            FROM diary_entries
            ORDER BY created_at DESC, id DESC
            """
        )
        rows = cur.fetchall()

    entries: list[dict] = []
    for row in rows:
        e = dict(row)
        e["id"] = e["id"]
        e["tags"] = _decode_tags(e.get("tags"))
        entries.append(_normalize_entry(e))

    return entries


# =========================
# 일정 관련 (SQLite 버전)
# =========================

class ScheduleItem(BaseModel):
    id: str
    date: str           # "YYYY-MM-DD"
    title: str          # 일정 제목
    memo: str | None = None
    time: str | None = None      # "HH:MM" (선택)
    time_str: str | None = None  # 문자열용 (선택)
    place: str | None = None     # 장소 (선택)


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


def load_schedule() -> List[ScheduleItem]:
    """일정 전체 로드 (SQLite)"""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, date, title, memo, time, time_str, place
            FROM schedule_items
            """
        )
        rows = cur.fetchall()

    items: list[ScheduleItem] = []
    for row in rows:
        item = ScheduleItem(
            id=row["id"],
            date=row["date"],
            title=row["title"],
            memo=row["memo"],
            time=row["time"],
            time_str=row["time_str"],
            place=row["place"],
        )
        # time / time_str 보정 (예전 JSON 로직 유지)
        if item.time and not item.time_str:
            item.time_str = item.time
        if item.time_str and not item.time:
            item.time = item.time_str
        items.append(item)

    items.sort(key=schedule_sort_key)
    return items


def save_schedule(items: List[ScheduleItem]) -> None:
    """일정 전체 저장 (SQLite, 전체 재저장 방식)"""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM schedule_items")
        for item in items:
            cur.execute(
                """
                INSERT INTO schedule_items (id, date, title, memo, time, time_str, place)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.date,
                    item.title,
                    item.memo,
                    item.time,
                    item.time_str,
                    item.place,
                ),
            )
        conn.commit()


# =========================
# 체크리스트 관련 (SQLite 버전)
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
    """SQLite 에서 TodoItem 리스트 로드."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, date, title, status
            FROM todos
            """
        )
        rows = cur.fetchall()

    items: list[TodoItem] = []
    for row in rows:
        status = row["status"]
        if status not in ("pending", "done", "giveup"):
            status = "pending"
        items.append(
            TodoItem(
                id=row["id"],
                date=row["date"],
                title=row["title"],
                status=status,
            )
        )
    return items


def save_todos(items: List[TodoItem]) -> None:
    """TodoItem 리스트를 SQLite 에 저장 (전체 재저장)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM todos")
        for item in items:
            cur.execute(
                """
                INSERT INTO todos (id, date, title, status)
                VALUES (?, ?, ?, ?)
                """,
                (item.id, item.date, item.title, item.status),
            )
        conn.commit()


# =========================
# 접속 제한(나만 보기)용 의존성
# =========================

def owner_only(credentials: HTTPBasicCredentials = Depends(security)):
    """
    HTTP Basic Auth 로 '주인만 접속'하게 막는 의존성.

    환경변수:
      STEPLOG_USER  : 아이디 (기본값: owner)
      STEPLOG_PASS  : 비밀번호 (기본값: change-me)
    """
    username = os.getenv("STEPLOG_USER", "squapple")
    password = os.getenv("STEPLOG_PASS", "september18!&")

    ok_user = secrets.compare_digest(credentials.username, username)
    ok_pass = secrets.compare_digest(credentials.password, password)

    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Not authorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True
