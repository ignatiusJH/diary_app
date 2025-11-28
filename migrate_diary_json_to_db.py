# migrate_diary_json_to_db.py

from datetime import datetime

from deps import load_all_entries, _parse_tags
from db import SessionLocal
from models import Diary


def main():
    session = SessionLocal()

    entries = load_all_entries()
    print(f"총 {len(entries)}개의 JSON 일기를 DB로 옮깁니다.")

    migrated = 0

    try:
        for data in entries:
            title = data.get("title") or ""
            content = data.get("content") or ""
            image_url = data.get("image_url")

            # tags: 리스트 or 문자열 모두 처리
            tags = data.get("tags") or []
            if isinstance(tags, list):
                tags_list = tags
            else:
                tags_list = _parse_tags(tags)

            tags_str = ", ".join(tags_list) if tags_list else ""

            created_at = None
            created_str = data.get("created_at")
            if created_str:
                try:
                    # 예: "2025-11-28 01:23"
                    created_at = datetime.strptime(created_str, "%Y-%m-%d %H:%M")
                except Exception:
                    # 형식이 다르면 그냥 None 으로 둠 → DB default 사용
                    created_at = None

            diary = Diary(
                title=title,
                content=content,
                image_url=image_url,
                tags=tags_str,
            )

            # created_at 있으면 덮어쓰기
            if created_at is not None:
                diary.created_at = created_at

            session.add(diary)
            migrated += 1

        session.commit()
        print(f"✅ 마이그레이션 완료: {migrated}개 일기 DB에 저장됨.")

    except Exception as e:
        session.rollback()
        print("❌ 에러 발생, 롤백합니다.")
        print(e)

    finally:
        session.close()


if __name__ == "__main__":
    main()
