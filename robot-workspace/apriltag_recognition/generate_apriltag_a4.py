#!/usr/bin/env python3
"""A4 인쇄용 AprilTag 36h11 ID 0 파일을 생성한다."""

from pathlib import Path

import cv2
import numpy as np


FAMILY = "DICT_APRILTAG_36h11"
TAG_ID = 0
TAG_MM = 180.0                 # 바깥 검은 사각형 한 변
DPI = 300
A4_MM = (210.0, 297.0)


def marker_cells() -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, FAMILY))
    marker = cv2.aruco.drawMarker(dictionary, TAG_ID, 800)
    # 36h11은 데이터 6x6 + 검은 테두리 1칸씩 = 총 8x8 셀이다.
    return marker.reshape(8, 100, 8, 100).mean(axis=(1, 3)) < 128


def write_svg(cells: np.ndarray, path: Path) -> None:
    x0 = (A4_MM[0] - TAG_MM) / 2
    y0 = 35.0
    cell = TAG_MM / 8
    rects = []
    for row in range(8):
        for col in range(8):
            if cells[row, col]:
                rects.append(
                    f'<rect x="{x0 + col * cell:.3f}" y="{y0 + row * cell:.3f}" '
                    f'width="{cell:.3f}" height="{cell:.3f}" fill="black"/>'
                )
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">
  <rect width="210" height="297" fill="white"/>
  {''.join(rects)}
  <text x="105" y="229" text-anchor="middle" font-family="sans-serif" font-size="5">AprilTag 36h11 · ID 0</text>
  <text x="105" y="237" text-anchor="middle" font-family="sans-serif" font-size="4">검은 바깥 사각형: 180 mm × 180 mm · 100% 실제 크기로 인쇄</text>
  <line x1="15" y1="248" x2="195" y2="248" stroke="black" stroke-width="0.3"/>
  <line x1="15" y1="246.5" x2="15" y2="249.5" stroke="black" stroke-width="0.3"/>
  <line x1="195" y1="246.5" x2="195" y2="249.5" stroke="black" stroke-width="0.3"/>
  <text x="105" y="255" text-anchor="middle" font-family="sans-serif" font-size="4">위 검증선도 180 mm여야 합니다</text>
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def write_png(cells: np.ndarray, path: Path) -> None:
    width = round(A4_MM[0] / 25.4 * DPI)
    height = round(A4_MM[1] / 25.4 * DPI)
    page = np.full((height, width), 255, dtype=np.uint8)
    tag_px = round(TAG_MM / 25.4 * DPI)
    marker = np.where(cells, 0, 255).astype(np.uint8)
    marker = cv2.resize(marker, (tag_px, tag_px), interpolation=cv2.INTER_NEAREST)
    x0 = (width - tag_px) // 2
    y0 = round(35 / 25.4 * DPI)
    page[y0:y0 + tag_px, x0:x0 + tag_px] = marker
    cv2.imwrite(str(path), page)


if __name__ == "__main__":
    output = Path("apriltag_36h11_id0_A4_180mm")
    cells = marker_cells()
    write_svg(cells, output.with_suffix(".svg"))
    write_png(cells, output.with_suffix(".png"))
    print(f"generated {output}.svg and {output}.png")
