# migrate_diary_json_to_db.py
# ----------------------------------------------------------
# 이 스크립트는 과거 JSON/SQLite 기반 일기 데이터를
# SQLAlchemy ORM 기반 Diary 테이블로 옮기는(마이그레이션) 용도이다.
#
# 딱 "한 번" 실행해서 이전 데이터를 옮기는 목적이며,
# 평소 앱 실행과는 무관하다.
# ----------------------------------------------------------

from datetime import datetime

from deps import load_all_entries, _parse_tags  # SQLite 기반 JSON/일기 불러오기 함수
from db import SessionLocal                     # SQLAlchemy DB 세션
from models import Diary                        # SQLAlchemy Diary 모델


def main():
    # SQLAlchemy 세션 생성
    session = SessionLocal()

    # SQLite 기반 diary_entries 테이블에서 모든 일기 로드
    entries = load_all_entries()
    print(f"총 {len(entries)}개의 JSON 일기를 DB로 옮깁니다.")

    migrated = 0  # 실제 저장된 일기 개수

    try:
        for data in entries:
            # JSON 에서 필요한 필드를 꺼낸다.
            title = data.get("title") or ""
            content = data.get("content") or ""
            image_url = data.get("image_url")

            # tags 는 list 또는 "," 문자열일 수 있어서 통일 처리
            tags = data.get("tags") or []
            if isinstance(tags, list):
                tags_list = tags
            else:
                tags_list = _parse_tags(tags)   # 예: "운동, 공부" → ["운동","공부"]

            # "운동, 공부" 형태의 문자열로 다시 저장
            tags_str = ", ".join(tags_list) if tags_list else ""

            # created_at 파싱 (문자열 → datetime)
            created_at = None
            created_str = data.get("created_at")
            if created_str:
                try:
                    # 예: "2025-11-28 01:23"
                    created_at = datetime.strptime(created_str, "%Y-%m-%d %H:%M")
                except Exception:
                    # 형식이 다르면 그냥 None → DB now() 사용
                    created_at = None

            # Diary ORM 객체 생성
            diary = Diary(
                title=title,
                content=content,
                image_url=image_url,
                tags=tags_str,
            )

            # created_at 값을 DB default(now()) 대신 기존 데이터로 덮어쓰기
            if created_at is not None:
                diary.created_at = created_at

            # 세션에 추가
            session.add(diary)
            migrated += 1

        # 전부 성공하면 commit
        session.commit()
        print(f"✅ 마이그레이션 완료: {migrated}개 일기 DB에 저장됨.")

    except Exception as e:
        # 중간에 문제 생기면 롤백
        session.rollback()
        print("❌ 에러 발생, 롤백합니다.")
        print(e)

    finally:
        # 세션 종료 (필수)
        session.close()


if __name__ == "__main__":
    # === 수정: 스크립트 진입점을 명확히 설명하는 주석 추가
    # 이 스크립트는 독립적으로 실행할 때만 동작한다.
    main()
