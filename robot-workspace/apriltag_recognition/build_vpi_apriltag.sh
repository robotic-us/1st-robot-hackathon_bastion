#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
suffix="$(python3-config --extension-suffix)"
g++ -O3 -DNDEBUG -Wall -Wextra -shared -std=c++17 -fPIC \
  $(python3-config --includes) -I/usr/include/pybind11 \
  -I/opt/nvidia/vpi3/include \
  vpi_apriltag.cpp -o "vpi_apriltag${suffix}" \
  -L/opt/nvidia/vpi3/lib/aarch64-linux-gnu \
  -Wl,-rpath,/opt/nvidia/vpi3/lib/aarch64-linux-gnu -lnvvpi

echo "built: vpi_apriltag${suffix}"
