#!/usr/bin/env bash
# =====================================================================
# recording_status.sh - is the Pi recording right now? Run on the Pi:
#     bash recording_status.sh
# Shows, for each camera: whether it's recording (newest file still growing),
# the newest file, how much is saved, plus free space on the SD card.
# =====================================================================
DIR=/var/lib/mediamtx/recordings

echo "MediaMTX service: $(systemctl is-active mediamtx 2>/dev/null || echo unknown)"
echo "Clock:            $(date '+%Y-%m-%d %H:%M:%S')  (synced: $(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown))"
echo "SD card free:     $(df -h "$DIR" 2>/dev/null | awk 'NR==2 {print $4 " of " $2}')"
echo

for cam in cam ir; do
  folder="$DIR/$cam"
  if [ ! -d "$folder" ]; then
    echo "[$cam] no recordings yet ($folder missing)"
    continue
  fi
  newest=$(ls -t "$folder"/*.mp4 2>/dev/null | head -n 1)
  count=$(ls "$folder"/*.mp4 2>/dev/null | wc -l)
  total=$(du -sh "$folder" 2>/dev/null | cut -f1)
  if [ -z "$newest" ]; then
    echo "[$cam] no recordings yet"
    continue
  fi
  age=$(( $(date +%s) - $(stat -c %Y "$newest") ))
  if [ "$age" -le 5 ]; then state="RECORDING"; else state="NOT RECORDING (last write ${age}s ago)"; fi
  echo "[$cam] $state"
  echo "       newest: $(basename "$newest")  $(du -h "$newest" | cut -f1)"
  echo "       saved:  $count files, $total"
done
