#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "sudo로 실행해야 합니다." >&2
  exit 1
fi

dir=/opt/ros/humble/lib/agx_phorce_bridge
dst=${dir}/phorce_monitor
backup=${dir}/phorce_monitor.id03-original
header=/opt/ros/humble/include/agx_pdo_contract/pdo_contract.hpp
header_backup=${header}.id03-original
official_sha=b84aa4c52fa0561c0d77ada50e8f353d570131af9d714c53fb15dbeb9f241815

[[ -f $backup ]] || { echo "공식 바이너리 백업 없음: $backup" >&2; exit 1; }
[[ $(sha256sum "$backup" | awk '{print $1}') == "$official_sha" ]] || {
  echo "공식 바이너리 백업 해시 불일치" >&2
  exit 1
}

install -m 0755 "$backup" "$dst"
setcap cap_net_admin,cap_net_raw,cap_sys_nice=ep "$dst"

if [[ -f $header_backup ]]; then
  cp -a "$header_backup" "$header"
fi

[[ $(sha256sum "$dst" | awk '{print $1}') == "$official_sha" ]]
getcap "$dst" | grep -q 'cap_net_admin,cap_net_raw,cap_sys_nice=ep'
echo "공식 phorce_monitor 복구 완료"
