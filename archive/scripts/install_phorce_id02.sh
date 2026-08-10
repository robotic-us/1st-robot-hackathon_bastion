#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "이 스크립트는 sudo로 실행해야 합니다." >&2
  exit 1
fi

src=/home/phorce/.local/lib/phorce-ids02-07/phorce_monitor
dst=/opt/ros/humble/lib/agx_phorce_bridge/phorce_monitor
backup=/opt/ros/humble/lib/agx_phorce_bridge/phorce_monitor.id03-original
header=/opt/ros/humble/include/agx_pdo_contract/pdo_contract.hpp
header_backup=/opt/ros/humble/include/agx_pdo_contract/pdo_contract.hpp.id03-original
original_sha=b84aa4c52fa0561c0d77ada50e8f353d570131af9d714c53fb15dbeb9f241815
single_axis_sha=ec95cc1f4a78d1f683c1b22b2a9a3b7b87dd4c144dae088ffa9e5f8bca8e68d1
patched_sha=f1f95be3e4bac1c7ad5ab5b228830873f694971e163bfe1e79e0b059264bd5db

actual_src=$(sha256sum "$src" | awk '{print $1}')
[[ $actual_src == "$patched_sha" ]] || {
  echo "패치 바이너리 해시 불일치: $actual_src" >&2
  exit 1
}

actual_dst=$(sha256sum "$dst" | awk '{print $1}')
if [[ $actual_dst == "$original_sha" ]]; then
  [[ -e $backup ]] || cp -a "$dst" "$backup"
elif [[ $actual_dst != "$single_axis_sha" && $actual_dst != "$patched_sha" ]]; then
  echo "설치 대상이 알려진 원본/패치 버전이 아닙니다: $actual_dst" >&2
  exit 1
fi

[[ -e $header_backup ]] || cp -a "$header" "$header_backup"
install -m 0755 "$src" "$dst"
setcap cap_net_admin,cap_net_raw,cap_sys_nice=ep "$dst"

# 설치 헤더도 ID 0x02..0x07 → bit0..5(0x003F) 프로파일과 일치시킨다.
sed -i \
  -e 's/CM_ECAT_EXPECTED_AXIS_MASK는 2026-08-01 현재 0x0002/CM_ECAT_EXPECTED_AXIS_MASK는 이 기체에서 0x003F/' \
  -e 's/CM_ECAT_EXPECTED_AXIS_MASK는 이 기체에서 0x0001/CM_ECAT_EXPECTED_AXIS_MASK는 이 기체에서 0x003F/' \
  -e 's/kCurrentPcmPoweredAxisMask = 0x0002u/kCurrentPcmPoweredAxisMask = 0x003Fu/' \
  -e 's/kCurrentPcmPoweredAxisMask = 0x0001u/kCurrentPcmPoweredAxisMask = 0x003Fu/' \
  "$header"

test "$(sha256sum "$dst" | awk '{print $1}')" = "$patched_sha"
getcap "$dst" | grep -q 'cap_net_admin,cap_net_raw,cap_sys_nice=ep'
grep -q 'kCurrentPcmPoweredAxisMask = 0x003Fu' "$header"

echo "설치 완료: motor ID 0x02..0x07 / axis mask 0x003F"
echo "원본 백업: $backup"
