#!/usr/bin/env bash
set -euo pipefail

# ===== 설정 =====
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="/media/squapple/574F41D61C94F39C/STEPLOG_backup"

echo "[STEPLOG RESTORE] 시작..."

# 백업 파일 목록 가져오기
shopt -s nullglob
BACKUPS=("$BACKUP_DIR"/steplog_backup_*.zip)
shopt -u nullglob

if [ ${#BACKUPS[@]} -eq 0 ]; then
  echo "❌ 복원 가능한 백업 파일이 없습니다. (${BACKUP_DIR})"
  exit 1
fi

echo
echo "사용 가능한 백업 목록:"
for i in "${!BACKUPS[@]}"; do
  idx=$((i+1))
  fname="$(basename "${BACKUPS[$i]}")"
  echo "  ${idx}) ${fname}"
done

echo
read -r -p "복원할 번호를 입력하세요 (그냥 Enter = 가장 마지막 번호): " choice

if [ -z "${choice:-}" ]; then
  # 아무것도 안 치면 마지막(가장 최신) 사용
  index=$((${#BACKUPS[@]} - 1))
else
  # 숫자 → 인덱스 변환
  if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
    echo "❌ 숫자를 입력해야 합니다."
    exit 1
  fi
  if [ "$choice" -lt 1 ] || [ "$choice" -gt ${#BACKUPS[@]} ]; then
    echo "❌ 1 ~ ${#BACKUPS[@]} 사이의 번호만 입력할 수 있습니다."
    exit 1
  fi
  index=$((choice - 1))
fi

SELECTED="${BACKUPS[$index]}"
echo
echo "선택된 백업: $(basename "$SELECTED")"
echo "프로젝트 경로: ${PROJECT_DIR}"
echo

# ===== 정말 복원할지 확인 (y / yes 둘 다 허용) =====
read -r -p "정말 이 백업으로 복원할까요? (y/N): " ans
case "${ans,,}" in
  y|yes)
    echo "복원 진행합니다..."
    ;;
  *)
    echo "복원 취소되었습니다."
    exit 0
    ;;
esac

# ===== 복원 실행 =====
cd "$PROJECT_DIR"

# 필요하다면 여기서 기존 파일 정리 로직 추가 가능
# 예: rm -rf data uploads  (이미 tar 안에 포함된 구조에 맞게 조정)

tar -xzf "$SELECTED" -C "$PROJECT_DIR"

echo
echo "[STEPLOG RESTORE] 완료!"
echo "=> ${SELECTED}"
