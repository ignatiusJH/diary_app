# db.py
# -------------------------------------------------------
# 이 파일은 SQLAlchemy(ORM)를 FastAPI와 연결시키는 핵심 설정 파일이다.
#
# 여기서 하는 일:
# 1) DATABASE_URL 로부터 DB 엔진(Postgres 또는 SQLite) 생성
# 2) SessionLocal (DB 세션 팩토리) 생성
# 3) Base (모든 ORM 모델의 부모 클래스) 선언
# 4) FastAPI 라우터에서 사용할 get_db() 의존성 제공
#
# 이 구조는 FastAPI + SQLAlchemy 조합에서 표준 패턴이다.
# -------------------------------------------------------

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# === 수정: override=True 버전은 필요 없으므로 주석 처리
# load_dotenv(override=True)
load_dotenv()


# =======================================================
# DATABASE_URL 설정
# =======================================================
# 기본값:
#   설정된 환경변수가 없으면 → "sqlite:///./steplog.db" 사용
#   (로컬 개발 환경용)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./steplog.db")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되어 있지 않습니다.")

# =======================================================
# SQLite / Postgres 구분
# =======================================================
# SQLAlchemy 는 여러 DB를 같은 API로 다룰 수 있지만,
# SQLite 는 thread 제한과 같은 특수 옵션이 필요하다.
#
# check_same_thread=False :
#   - FastAPI의 비동기 환경에서 SQLite 사용 시 필수
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}


# =======================================================
# 엔진 생성: SQLAlchemy의 "핵심"
# =======================================================
# create_engine() 는 실제 DB와의 연결을 관리하는 객체를 만든다.
# - echo=False : SQL 로그 출력 여부 (True면 쿼리가 다 출력됨)
# - future=True : SQLAlchemy 2.0 스타일 사용
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
)


# =======================================================
# SessionLocal: DB 세션을 만들어주는 factory
# =======================================================
# autocommit=False:
#   - commit() 을 직접 호출해야 DB에 반영됨 (안전)
# autoflush=False:
#   - 세션이 DB 상태를 자동으로 동기화하지 않음
# bind=engine:
#   - 이 세션이 어떤 DB 엔진과 연결되는지 지정
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# =======================================================
# Base: 모든 ORM 모델이 상속받는 부모 클래스
# =======================================================
# models.py 에서 모델 정의할 때 Base 를 상속하면
# Base.metadata 에 테이블 정보가 자동으로 등록된다.
Base = declarative_base()


# =======================================================
# get_db: FastAPI 라우터에서 DB 세션을 의존성 주입하는 함수
# =======================================================
def get_db():
    """
    FastAPI 엔드포인트에서 DB 세션을 제공하는 함수.

    예)
        @router.get("/")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Model).all()

    원리:
    - API 요청이 들어오면 SessionLocal() 로 새 세션을 하나 만들고
    - 라우터 함수에 전달한 뒤
    - 요청이 끝나면 finally: db.close() 로 세션을 반드시 닫는다.

    이렇게 해야 connection leak(세션이 안 닫힘)을 방지할 수 있다.
    """

    from sqlalchemy.orm import Session

    db: Session = SessionLocal()
    try:
        yield db  # 라우터 함수로 전달되는 부분
    finally:
        db.close()  # 요청이 끝난 뒤 DB 연결 종료
