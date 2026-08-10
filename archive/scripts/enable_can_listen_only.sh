#!/usr/bin/env bash
set -euo pipefail

for iface in can0 can1; do
  ip link set "$iface" down
  ip link set "$iface" type can bitrate 1000000 dbitrate 5000000 fd on listen-only on
  ip link set "$iface" up
done

ip -details link show can0
ip -details link show can1
