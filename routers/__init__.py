# routers/__init__.py
# -----------------------------------------------------------
# 이 파일은 "routers" 폴더를 패키지처럼 사용할 수 있게 해주는
# __init__.py 파일이다.
#
# FastAPI의 라우터들을 한 곳에서 모아서 main.py 에서
# 깔끔하게 import 할 수 있도록 정리하는 역할을 한다.
#
# main.py 에서는 이렇게 쓴다:
#   from routers import diary_router, schedule_router, ...
#
# 이게 가능한 이유가 바로 이 __init__.py 파일 때문이다.
# -----------------------------------------------------------

# 일기 기능 라우터 (/diary 이하)
from .diary import router as diary_router

# 일정 기능 라우터 (/schedule 이하)
from .schedule import router as schedule_router

# 체크리스트(Todo) 기능 라우터 (/todos 이하)
from .todos import router as todos_router

# 통계 페이지 라우터 (/stats 이하)
from .stats import router as stats_router

# 백업 다운로드 라우터 (/backup/db)
from .backup import router as backup_router

# 복원 업로드 라우터 (/restore/db)
from .restore_router import router as restore_router
