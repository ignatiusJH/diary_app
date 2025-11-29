# models.py
# ----------------------------------------------
# 이 파일은 SQLAlchemy ORM 모델 정의 파일이다.
# 각 테이블의 구조를 "클래스" 형태로 설계해두고,
# 이를 통해 DB의 레코드를 파이썬 객체처럼 다룰 수 있게 된다.
# ----------------------------------------------

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func

from db import Base  # SQLAlchemy Base (모델 등록용)


# ==========================================================
# Diary 모델 (현재는 거의 사용되지 않는 옛 구조)
# ==========================================================
class Diary(Base):
    """
    과거 Diary 라우터를 테스트용으로 운영하던 시절 모델.
    실제 앱 기능은 SQLite(diary_entries) 기반이므로 거의 사용되지 않는다.

    - 남겨두는 이유:
      혹시 미래에 Diary 기능을 SQLAlchemy 기반으로 확장할 때 재사용 가능.
    """

    __tablename__ = "diaries"

    # 고유 번호 (자동 증가)
    id = Column(Integer, primary_key=True, index=True)

    # 일기 제목
    title = Column(String(200), nullable=False)

    # 일기 내용
    content = Column(Text, nullable=False)

    # 태그(쉼표 구분 문자열 형태)
    tags = Column(String(200), nullable=True)

    # 업로드된 이미지 URL
    image_url = Column(String(300), nullable=True)

    # 생성 시각 (서버가 자동으로 now() 넣어줌)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ==========================================================
# Schedule 모델
# ==========================================================
class Schedule(Base):
    """
    일정(schedules) 테이블 모델.

    - 대시보드, 일정 페이지 모두 이 모델을 통해 데이터 로드/저장.
    """

    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)

    # 일정 날짜: YYYY-MM-DD 문자열
    date = Column(String(10), nullable=False)

    # 일정 제목
    title = Column(String(200), nullable=False)

    # 일정 메모 (선택)
    memo = Column(Text, nullable=True)

    # 시간 정보 문자열 ("14:00")
    time_str = Column(String(20), nullable=True)

    # 장소 정보
    place = Column(String(200), nullable=True)

    # 일정 완료 여부 (현재 앱에서는 사실상 거의 사용하지 않는 필드)
    done = Column(Boolean, default=False)


# ==========================================================
# Todo 모델
# ==========================================================
class Todo(Base):
    """
    체크리스트(todos) 테이블 모델.

    - 모든 Todo 들은 이 모델 기반으로 저장된다.
    - 정렬(order)과 상태(status) 컬럼이 핵심.
    """

    __tablename__ = "todos"

    # uuid 문자열 그대로 사용
    id = Column(String(100), primary_key=True, index=True)

    # 날짜 문자열: YYYY-MM-DD
    date = Column(String(10), nullable=False)

    # 할 일 제목
    title = Column(String(200), nullable=False)

    # 상태: pending / done / giveup
    status = Column(String(20), nullable=False, default="pending")

    # 순서 정렬용 (진행 중 항목은 0부터)
    order = Column(Integer, nullable=False, default=0)

    # === 수정: 이 필드는 현재 실제 로직에서는 사용되지 않는다.
    #           DB 마이그레이션 테스트용으로 남아있던 필드이므로
    #           사용하지 않는다는 것을 명확히 표시해준다.
    #           (주석만 추가했으며 기능은 그대로 유지)
    # ❗ 실제 정렬은 order 컬럼에서 관리한다.
    sort_index = Column(Integer, nullable=False, default=0)  # ← 현재 앱에서는 사용되지 않음
