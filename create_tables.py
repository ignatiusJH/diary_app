# create_tables.py
# ----------------------------------------------------------
# 이 스크립트는 "SQLAlchemy ORM 모델(models.py)"을 기반으로
# 데이터베이스에 테이블을 생성하는 용도다.
#
# Render/운영 서버에서는 main.py 의 startup 이벤트에서
# Base.metadata.create_all()을 실행하므로 보통 필요 없지만,
# 로컬 개발할 때 DB 구조를 한 번에 초기화하고 싶을 때 유용하다.
# ----------------------------------------------------------

from db import Base, engine
import models  # models.py 안의 ORM 클래스를 Base에 등록하기 위해 import 한다.


# === 수정: 출력에서 불필요한 이모지 제거 (PDF 등과 혼동 방지 목적)
print("Creating tables...")

# Base.metadata.create_all()
# - Base에 등록된 모든 ORM 모델(Diary, Schedule, Todo)을 기준으로
#   테이블이 없으면 생성한다.
# - 존재하는 테이블은 건드리지 않는다.
Base.metadata.create_all(bind=engine)

print("Done.")
