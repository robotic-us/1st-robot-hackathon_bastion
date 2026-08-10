# 바스티온 — 제1회 로봇 해커톤 2026

제1회 로봇 해커톤(2026. 8. 5.~8. 8., KAIST)에 참가한 **바스티온** 팀의 로봇 제어·비전·모션 작업물입니다.

- 팀: 바스티온 (KAIST)
- 팀원: 서승재 · 정찬교 · 박찬
- 주최: 로보틱어스(Roboticus)
- 대회 안내: https://robotic-us.com

행사 현장에서 사용한 Jetson/PhORCE 개발 환경의 소스, 모션 데이터, 운영 도구와 문서를 한곳에 보존했습니다. 저장소 최상단의 각 폴더가 원래 작업 영역을 나타내며, 생성된 빌드 결과물과 캐시는 제외했습니다.

## 주요 작업물

| 경로 | 내용 |
| --- | --- |
| [`robot-workspace/`](robot-workspace/) | ROS 2 기반 로봇 제어, 모션 GUI, AprilTag 추종, 태양 고도 기반 모션 선택기와 모션 CSV |
| [`pcm/`](pcm/) | PCM 상대교시 도구, 배포 묶음과 SD 카드 모션 백업 |
| [`scripts/`](scripts/) | PhORCE 진단, 복구, 패치, CAN 점검 및 6축 제어 보조 스크립트 |
| [`documents/`](documents/) | 운영 메모와 해커톤 추가 공지 자료 |
| [`packages/`](packages/) | 행사 당시 사용한 AGR/PhORCE SDK 업데이트 패키지 |
| [`misc/`](misc/) | 독립적으로 작성된 PCM 제어 보조 코드 |

## 기능별 시작점

- 사람을 따라가는 AprilTag 운반 로봇: [`robot-workspace/apriltag_recognition/README.md`](robot-workspace/apriltag_recognition/README.md)
- 베이스 주행 모션과 슬롯 구성: [`robot-workspace/base_movement/README.md`](robot-workspace/base_movement/README.md)
- PhORCE 모션 그래프 GUI: [`robot-workspace/motion_tree_gui/README.md`](robot-workspace/motion_tree_gui/README.md)
- 6축 실시간 상대각 제어: [`robot-workspace/relative_angle/README.md`](robot-workspace/relative_angle/README.md)
- 태양 고도 기반 모션 선택: [`robot-workspace/sun_elevation_motion/README.md`](robot-workspace/sun_elevation_motion/README.md)
- PCM 상대교시 배포 묶음: [`pcm/relative-teaching-bundle/pcm_relative_teaching_bundle/README.md`](pcm/relative-teaching-bundle/pcm_relative_teaching_bundle/README.md)

각 기능의 요구 환경과 실행법은 해당 폴더의 README를 확인하세요. 일부 문서의 `/home/phorce/bastion_ws` 경로는 행사 컴퓨터에서 사용한 원래 경로이므로, 다른 컴퓨터에서는 체크아웃한 위치에 맞춰 바꿔야 합니다.

## 안전 주의

이 저장소에는 실제 액추에이터와 바퀴를 움직이는 코드 및 모션 데이터가 포함되어 있습니다. 실제 로봇에서 실행하기 전에 다음 사항을 확인하세요.

1. 물리 E-Stop을 즉시 누를 수 있는 상태로 준비합니다.
2. 로봇을 받침대에 띄우거나 충분한 안전거리를 확보합니다.
3. ROS 도메인, 축 매핑, PCM 모션 슬롯과 현재 절대각이 문서의 전제와 일치하는지 확인합니다.
4. 가능한 기능은 dry-run 또는 비전 전용 모드로 먼저 검증합니다.

## 보존 범위

행사 컴퓨터 포맷 전에 Git 외부에서 발견된 관련 작업물을 함께 정리했습니다. 원래 작업 구조는 최대한 유지했지만 다음 항목은 저장소에 포함하지 않았습니다.

- ROS `build/`, `install/`, `log/`
- Python 캐시 및 컴파일 산출물
- 데스크톱 설치 파일과 원격 데스크톱 녹화
- 운영체제 및 애플리케이션 상태 파일

## 지적재산권

> 본 프로젝트의 지적재산권은 바스티온 팀(팀원 전원)에게 있으며, 본 대회의 주최 측(로보틱어스)은 아카이브 및 홍보 목적으로만 본 저장소를 활용합니다.

별도 `LICENSE` 파일이 추가되기 전까지는 일반적인 오픈 소스 라이선스가 부여된 것으로 간주하지 않습니다.
