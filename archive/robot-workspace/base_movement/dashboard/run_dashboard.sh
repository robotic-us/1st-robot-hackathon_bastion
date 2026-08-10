#!/usr/bin/env bash
set -euo pipefail
cd /home/phorce/bastion_ws/base_movement
exec python3 dashboard/server.py --domain-id 21 "$@"
