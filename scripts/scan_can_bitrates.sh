#!/usr/bin/env bash
set -u

iface=can0
configs=(
  "1000000 8000000"
  "1000000 5000000"
  "1000000 4000000"
  "1000000 2000000"
  "500000 5000000"
  "500000 4000000"
  "500000 2000000"
  "500000 1000000"
  "250000 2000000"
  "250000 1000000"
)

for config in "${configs[@]}"; do
  read -r nominal data <<<"$config"
  ip link set "$iface" down
  if ! ip link set "$iface" type can bitrate "$nominal" dbitrate "$data" fd on listen-only on; then
    echo "SKIP nominal=$nominal data=$data"
    continue
  fi
  ip link set "$iface" up
  echo "TEST nominal=$nominal data=$data"
  frame=$(timeout 2 candump -L -n 1 "$iface" 2>/dev/null || true)
  if [[ -n "$frame" ]]; then
    echo "FOUND nominal=$nominal data=$data"
    echo "$frame"
    exit 0
  fi
done

echo "NO_FRAMES"
exit 2
