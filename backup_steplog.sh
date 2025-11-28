#!/usr/bin/env bash

set -euo pipefail

# 프로젝트 루트 디렉토리
PROJECT_DIR="/home/squapple/dev/diary_app"

# 백업 저장 디렉토리 (저장용 드라이브)
BACKUP_DIR="/media/squapple/574F41D61C94F39C/STEPLOG_backup"

# 타임스탬프 (예: 20251129_013045)
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"

# 최종 백업 파일 경로
ARCHIVE_NAME="steplog_backup_${TIMESTAMP}.zip"
ARCHIVE_PATH="${BACKUP_DIR}/${ARCHIVE_NAME}"

echo "[STEPLOG BACKUP] 시작..."
echo "  프로젝트 : ${PROJECT_DIR}"
echo "  백업파일 : ${ARCHIVE_PATH}"

cd "${PROJECT_DIR}"

# 백업 대상 목록
INCLUDE=()

# SQLite DB
if [ -f "data/steplog.db" ]; then
  INCLUDE+=("data/steplog.db")
fi

# 업로드된 이미지들
if [ -d "uploads" ]; then
  INCLUDE+=("uploads")
fi

# .env (있으면 같이 보관)
if [ -f ".env" ]; then
  INCLUDE+=(".env")
fi

if [ ${#INCLUDE[@]} -eq 0 ]; then
  echo "백업할 대상이 없습니다."
  exit 1
fi

# 백업 저장 폴더가 없으면 생성
mkdir -p "${BACKUP_DIR}"

# tar.gz 로 압축
tar -czf "${ARCHIVE_PATH}" "${INCLUDE[@]}"

echo "[STEPLOG BACKUP] 완료!"
echo "  => ${ARCHIVE_PATH}"
