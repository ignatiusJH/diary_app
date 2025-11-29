# deps.py
# ---------------------------------------------
# 이 파일은 전체 앱에서 공통으로 쓰이는 것들을 모아둔 곳이다.
# - 경로/디렉터리 상수 (uploads, static, data 등)
# - 옛날 SQLite 기반 일기(diary) 관련 함수
# - SQLAlchemy 기반 일정(Schedule) / 체크리스트(Todo) 로드/저장 함수
# - Basic Auth(아이디/비번) 의존성
# ---------------------------------------------

from pathlib import Path
# === 수정: datetime 은 이 파일에서 사용하지 않아서 제거해도 된다.
#           date 만 사용되므로, 불필요한 import 를 줄여줌.
from datetime import date
import json
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

# SQLAlchemy 세션 / ORM 모델
from db import SessionLocal
from models import Schedule, Todo  # models.py 에 정의한 ORM 클래스 사용


# =========================
# 공통 경로 / 상수
# =========================

# 현재 파일(deps.py)이 있는 폴더 기준으로 경로를 잡는다.
BASE_DIR = Path(__file__).resolve().parent

# 업로드 이미지가 저장될 디렉터리
UPLOAD_DIR = BASE_DIR / "uploads"
# 기타 데이터 파일이 들어가는 디렉터리
DATA_DIR   = BASE_DIR / "data"
# CSS/JS/이미지 같은 정적 파일 디렉터리
STATIC_DIR = BASE_DIR / "static"

# 디렉터리가 없으면 자동으로 만들어 둔다.
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# SQLite DB 경로 (일기용 – 옛날 구조를 유지하기 위해 남겨둔 것)
#   주의: 일정/체크리스트는 SQLAlchemy(Postgres/SQLite) 쪽을 쓰고,
#         이 DB는 diary_entries 테이블에만 사용된다.
DB_PATH = DATA_DIR / "steplog.db"

# 목록 화면 페이지당 개수 (리스트/갤러리/히스토리 등)
ITEMS_PER_PAGE_LIST    = 10
ITEMS_PER_PAGE_GALLERY = 50
HISTORY_ITEMS_PER_PAGE = 20  # 체크리스트 완료/포기 히스토리 페이지당 개수

# JSON 파일 경로 (과거 JSON 기반 데이터 구조를 위해 남겨둔 상수)
#   지금 메인 기능은 모두 DB 기반이지만,
#   백업/마이그레이션 스크립트에서 사용할 수 있어서 그대로 두었다.
SCHEDULE_FILE = DATA_DIR / "schedule.json"   # 일정
TODOS_FILE    = DATA_DIR / "todos.json"      # 체크리스트

# .env 파일에서 환경변수 로드 (DIARY_USER 등)
load_dotenv()

# HTTP Basic 인증 객체
security = HTTPBasic()

# Jinja 템플릿 엔진 (templates/ 폴더를 기준으로 템플릿을 찾는다)
templates = Jinja2Templates(directory="templates")


# =========================
# (구) SQLite DB 유틸 – 일기용
# =========================

def get_connection() -> sqlite3.Connection:
    """
    옛날 일기/백업 코드에서 쓰는 로컬 SQLite 연결 함수.

    - diary_entries 테이블을 사용하는 용도에만 사용한다.
    - 일정(Schedule) / 체크리스트(Todo)는 SQLAlchemy 세션을 사용하므로
      여기 연결과는 별개이다.
    """
    conn = sqlite3.connect(DB_PATH)
    # row 를 dict 처럼 사용할 수 있게 해 주는 설정
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    앱 시작 시 한 번만 호출해서, diary_entries 테이블이 없으면 생성한다.
    (SQLAlchemy 가 아닌, 순수 SQLite 쿼리를 쓰는 부분)
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # 일기 테이블 (id 기준으로 upsert 하는 구조)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS diary_entries (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                image_url  TEXT,
                created_at TEXT,
                updated_at TEXT,
                tags       TEXT   -- JSON 문자열 (리스트를 문자열로 저장)
            )
            """
        )

        conn.commit()


# 모듈이 import 될 때 자동으로 한 번 실행해서
# diary_entries 테이블이 없으면 만들어 둔다.
init_db()


# =========================
# 인증
# =========================

def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """
    전체 앱에 공통으로 걸 인증 의존성.
    - main.py 에서 FastAPI(dependencies=[Depends(require_auth)]) 로 설정되어 있음.
    - 브라우저에서 아이디/비번을 물어보는 가장 기본적인 Basic Auth 방식.

    ID/PW 는 .env 파일에 넣어 두고 사용:
      DIARY_USER, DIARY_PASSWORD
    """
    correct_user = os.getenv("DIARY_USER")
    correct_pass = os.getenv("DIARY_PASSWORD")

    # 환경변수가 설정되지 않았다면 서버 설정 문제이므로 500 에러
    if not correct_user or not correct_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth env vars (DIARY_USER / DIARY_PASSWORD) are not set.",
        )

    # 아이디/비밀번호가 하나라도 다르면 401 Unauthorized
    if credentials.username != correct_user or credentials.password != correct_pass:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # 필요하면 이 값을 핸들러에서 쓸 수 있음 (현재는 단순 인증 체크용)
    return credentials.username


# =========================
# 공통 유틸 (기록)
# =========================

def _normalize_entry(entry: dict) -> dict:
    """
    기록(일기) 형식을 정리해 주는 함수.

    - 줄바꿈을 LF(\n) 기반으로 통일
    - tags 필드를 항상 리스트로 맞춰줌
      (문자열이면 쉼표로 split 해서 리스트로 변환)
    """
    content = entry.get("content") or ""
    if isinstance(content, str):
        # 윈도우 스타일(\r\n)을 유닉스 스타일(\n)로 통일
        entry["content"] = content.replace("\r\n", "\n")

    tags = entry.get("tags") or []
    if isinstance(tags, str):
        # "a, b, c" → ["a", "b", "c"]
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    entry["tags"] = tags

    return entry


def _parse_tags(text: str) -> list[str]:
    """
    텍스트로 들어온 태그(쉼표 구분)를 리스트로 변환.
    예: "운동, 일기" → ["운동", "일기"]
    """
    if not text:
        return []
    return [t.strip() for t in text.split(",") if t.strip()]


# =========================
# 일기(기록) 관련: SQLite 버전
# =========================

def _decode_tags(tags_raw: str | None) -> list[str]:
    """
    DB에 저장된 tags 필드를 파이썬 리스트로 변환.

    - JSON 문자열이면 json.loads 로 변환
    - JSON 이 아니면 그냥 쉼표 구분 문자열이라고 보고 파싱
    """
    if not tags_raw:
        return []
    try:
        return json.loads(tags_raw)
    except json.JSONDecodeError:
        # 예전 형식이거나 그냥 문자열일 경우
        return _parse_tags(tags_raw)


def load_entry(entry_id: str) -> dict:
    """
    단일 일기 1개 로드 (SQLite).

    - diary_entries 테이블에서 id 로 한 건을 가져온다.
    - 태그/줄바꿈 포맷을 _decode_tags / _normalize_entry 로 정리해서 반환한다.
    """
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
    단일 일기 1개 저장 (INSERT 또는 UPDATE).

    - id 가 없으면 새로 INSERT
    - id 가 이미 있으면 UPDATE (ON CONFLICT 절을 이용)
    """
    # 원본 딕셔너리를 건드리지 않기 위해 copy() 후 정규화
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
    """
    단일 일기 1개 삭제 (SQLite).
    - id 에 해당하는 row 를 DELETE.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM diary_entries WHERE id = ?", (entry_id,))
        conn.commit()


def load_all_entries() -> list[dict]:
    """
    전체 일기 목록 로드 (최신순).

    - diary_index 화면에서 목록/검색용으로 사용.
    - created_at 기준 내림차순 → id 내림차순 순으로 정렬.
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
# 일정 관련 – SQLAlchemy 버전
# =========================

class ScheduleItem(BaseModel):
    """
    화면/백업 등에서 사용하기 위한 일정 DTO(Data Transfer Object).

    - ORM 객체(Schedule) 그대로 쓰지 않고,
      필요한 필드만 뽑아서 Pydantic 모델로 옮겨 담는다.
    """
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
    2) 같은 날짜 안에서는 '시간 없음'이 먼저 온다.
    3) 그 다음에 시간(HH:MM) 오름차순

    → 이렇게 하면 "날짜별로 위에서 아래로 자연스러운 일정 리스트"가 만들어진다.
    """
    # 문자열("YYYY-MM-DD") → date 객체
    d = date.fromisoformat(item.date)

    # time_str 또는 time 필드 중 하나를 사용
    t_str = (item.time_str or item.time or "").strip()

    if t_str:
        try:
            h, m = map(int, t_str.split(":"))
        except ValueError:
            # 시간 파싱이 실패하면 가장 뒤로 밀기 위해 23:59 로 취급
            h, m = 23, 59
        # has_time=1 이면 시간 있음 → 날짜 안에서 뒤쪽으로
        has_time = 1
    else:
        # 시간 정보가 없는 일정은 has_time=0 으로 해서 날짜 안에서 먼저 오게 함
        h, m = 0, 0
        has_time = 0

    return (d, has_time, h, m)


def load_schedule() -> List[ScheduleItem]:
    """
    일정 전체 로드 – SQLAlchemy schedules 테이블 사용.

    - / (대시보드), /schedule, /backup 등에서
      모두 이 함수를 통해 같은 일정 데이터를 보게 된다.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Schedule)
            .order_by(Schedule.date, Schedule.title)
            .all()
        )

        items: list[ScheduleItem] = []
        for row in rows:
            # row.date 가 date 객체일 수도 있고, 문자열일 수도 있으므로 통일
            if isinstance(row.date, date):
                date_str = row.date.isoformat()
            else:
                date_str = str(row.date)

            time_str = getattr(row, "time_str", None)
            time_raw = getattr(row, "time", None)
            if not time_str and time_raw:
                time_str = str(time_raw)

            items.append(
                ScheduleItem(
                    id=str(row.id),
                    date=date_str,
                    title=row.title,
                    memo=row.memo,
                    time=time_raw,
                    time_str=time_str,
                    place=row.place,
                )
            )

        # 위에서 만든 ScheduleItem 리스트를 우리가 정의한 키로 정렬
        items.sort(key=schedule_sort_key)
        return items
    finally:
        db.close()


def save_schedule(items: List[ScheduleItem]) -> None:
    """
    일정 전체 저장 – schedules 테이블을 '통째로 갈아끼우는' 방식.

    - 기존 데이터를 모두 삭제한 뒤,
    - 전달받은 items 리스트를 순서대로 다시 INSERT 한다.
    """
    db = SessionLocal()
    try:
        # 기존 일정 전부 삭제
        db.query(Schedule).delete()

        for it in items:
            # id 가 숫자로 넘어올 수도 있고, 문자열일 수도 있어서 한 번 정리
            try:
                int_id = int(it.id)
            except (TypeError, ValueError):
                int_id = None

            time_str = it.time_str or it.time

            row = Schedule(
                id=int_id,
                date=it.date,
                title=it.title,
                memo=it.memo,
                time_str=time_str,
                place=it.place,
            )
            db.add(row)

        db.commit()
    finally:
        db.close()


# =========================
# 체크리스트 관련 – SQLAlchemy 버전
# =========================
# status 값은 항상 이 셋만 사용:
# - "pending" : 진행 중
# - "done"    : 완료
# - "giveup"  : 포기

class TodoItem(BaseModel):
    """
    화면/백업에서 사용하는 Todo DTO.
    """
    id: str
    date: str          # "YYYY-MM-DD"
    title: str
    status: str = "pending"  # "pending" / "done" / "giveup"


def load_todos() -> List[TodoItem]:
    """
    SQLAlchemy todos 테이블에서 TodoItem 리스트 로드.

    ★ 핵심: 여기서 order 컬럼을 기준으로 정렬해 준다.
      - /todos 화면의 '진행 중' 리스트
      - 대시보드의 오늘 체크리스트
      둘 다 이 순서를 그대로 사용한다.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Todo)
            .order_by(Todo.date, Todo.order, Todo.id)  # order 기준 정렬
            .all()
        )

        items: list[TodoItem] = []
        for row in rows:
            if isinstance(row.date, date):
                date_str = row.date.isoformat()
            else:
                date_str = str(row.date)

            status = row.status or "pending"
            if status not in ("pending", "done", "giveup"):
                status = "pending"

            items.append(
                TodoItem(
                    id=str(row.id),
                    date=date_str,
                    title=row.title,
                    status=status,
                )
            )

        return items
    finally:
        db.close()


def save_todos(items: List[TodoItem]) -> None:
    """
    TodoItem 리스트를 todos 테이블에 저장 (전체 재저장).

    - /todos 화면에서 새로 추가 / 제목 수정 / 순서 조정할 때 사용.
    - 순서는 items 리스트의 순서를 기준으로:
        * 진행 중(pending)인 항목만 0,1,2,... 의 order 를 부여
        * 완료/포기 항목은 큰 번호(100000+)를 줘서 뒤쪽으로 밀어 둔다.
    """
    db = SessionLocal()
    try:
        # 기존 todo 를 모두 지우고 새로 채운다.
        db.query(Todo).delete()

        # 진행 중 / 그 외 상태 분리
        pending_items = [it for it in items if it.status == "pending"]
        other_items   = [it for it in items if it.status != "pending"]

        # 진행 중: order = 0,1,2,...
        for idx, it in enumerate(pending_items):
            row = Todo(
                id=it.id,
                date=it.date,
                title=it.title,
                status=it.status,
                order=idx,
            )
            db.add(row)

        # 완료/포기: order = 100000 + idx (순서가 크게 중요하지 않은 애들)
        base = 100000
        for idx, it in enumerate(other_items):
            row = Todo(
                id=it.id,
                date=it.date,
                title=it.title,
                status=it.status,
                order=base + idx,
            )
            db.add(row)

        db.commit()
    finally:
        db.close()


# =========================
# 접속 제한(나만 보기)용 의존성
# =========================

def owner_only(credentials: HTTPBasicCredentials = Depends(security)):
    """
    HTTP Basic Auth 로 '주인만 접속'하게 막는 의존성.

    - 특정 라우트에서 Depends(owner_only) 를 걸어두면
      지정된 ID/PW 가 아니면 접근이 차단된다.

    환경변수:
      STEPLOG_USER  : 아이디 (기본값: squapple)
      STEPLOG_PASS  : 비밀번호 (기본값: september18!&)
    """
    username = os.getenv("STEPLOG_USER", "squapple")
    password = os.getenv("STEPLOG_PASS", "september18!&")

    # 문자열 비교 시 timing attack 을 막기 위해 compare_digest 사용
    ok_user = secrets.compare_digest(credentials.username, username)
    ok_pass = secrets.compare_digest(credentials.password, password)

    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Not authorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True
