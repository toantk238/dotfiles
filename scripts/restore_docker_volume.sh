#!/bin/bash
# restore.sh
# Usage: ./restore.sh <backup.tar.gz> <volume_name>
# Example: ./restore.sh backup.tar.gz vaultwarden_vw-data

BACKUP_FILE="${1:?Usage: $0 <backup.tar.gz> <volume_name>}"
VOLUME_NAME="${2:?Usage: $0 <backup.tar.gz> <volume_name>}"

echo "==> Checking backup structure..."
tar -tzf "$BACKUP_FILE" | head -20

echo ""
echo "==> Restoring '$BACKUP_FILE' into volume '$VOLUME_NAME'..."

docker run --rm \
  -v "$VOLUME_NAME":/restore \
  -v "$(pwd)/$BACKUP_FILE":/backup.tar.gz \
  alpine \
  sh -c "cd /restore && tar -xzf /backup.tar.gz --strip-components=2"
  # --strip-components=2 strips "backup/vw-data/" prefix
  # Adjust the number based on what `tar -tzf` shows above

echo ""
echo "==> Done! Contents of restored volume:"
docker run --rm \
  -v "$VOLUME_NAME":/restored \
  alpine ls -la /restored
