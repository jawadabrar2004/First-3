#!/usr/bin/env bash
# =====================================================================
# prune_recordings.sh - keep the SD card from filling up.
#
# MediaMTX records both cameras non-stop (about 1 GB per hour together).
# This deletes the OLDEST recordings, one file at a time, only while free
# space is below MIN_FREE_MB. Recordings are never deleted just for being old.
#
# Runs every minute from a systemd timer (installed by setup_mediamtx.sh).
# Run it by hand:  sudo bash prune_recordings.sh
# =====================================================================
set -euo pipefail

DIR=${RECORDINGS_DIR:-/var/lib/mediamtx/recordings}   # (override only for testing)
MIN_FREE_MB=${MIN_FREE_MB:-4096}   # keep at least 4 GB free
KEEP_RECENT_S=120                  # never touch files written in the last 2 minutes

[ -d "$DIR" ] || exit 0
log() { command -v logger >/dev/null && logger -t prune_recordings "$1" || echo "$1"; }

free_mb() { df -Pm "$DIR" | awk 'NR==2 {print $4}'; }

while [ "$(free_mb)" -lt "$MIN_FREE_MB" ]; do
  # Oldest file by modification time (works even if the clock was wrong at boot)
  oldest=$(find "$DIR" -type f -name '*.mp4' -printf '%T@ %p\n' | sort -n | head -n 1)
  [ -n "$oldest" ] || break                     # nothing left to delete
  mtime=${oldest%% *}
  file=${oldest#* }
  if [ $(( $(date +%s) - ${mtime%.*} )) -lt "$KEEP_RECENT_S" ]; then
    log "SD card nearly full but only recent recordings are left; not deleting"
    break
  fi
  rm -f -- "$file"
  log "deleted $file to keep ${MIN_FREE_MB} MB free"
done

# Tidy up empty folders (never the top folder)
find "$DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true
