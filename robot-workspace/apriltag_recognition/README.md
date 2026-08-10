# AprilTag 양산 운반 로봇

웹캠으로 사람에게 부착한 AprilTag를 찾아 상대 거리와 좌우 각도를 계산하고, 그 결과를
phorce 모션 슬롯에 매핑하는 최소 구현입니다. **기본 실행은 로봇을 움직이지 않습니다.**

## 1. 카메라 보정

9×6 내부 코너 체커보드(칸 크기 예: 24 mm)를 준비합니다.

```bash
python3 calibrate_camera.py --cols 9 --rows 6 --square-m 0.024
```

서로 다른 위치와 기울기에서 `Space`를 20번 누릅니다. 렌즈나 해상도를 바꾸면 다시
보정해야 합니다.

## 2. 태그와 설정

제공된 `apriltag_36h11_id0_A4_180mm.svg`를 **100% 실제 크기**로 출력해 사람의
몸통처럼 잘 보이는 곳에 평평하게 고정합니다. 브라우저나 인쇄 창의 “페이지에 맞춤”은
끄세요. 출력 후 검은 바깥 사각형 한 변과 아래 검증선이 모두 180 mm인지 자로 확인합니다.
설정의 `tag.size_m`은 이에 맞춰 `0.18`입니다.

```bash
cp config.example.json config.json
```

먼저 `motion` 값은 `null`로 둡니다. 카메라 좌우가 반대로 장착됐다면
`TURN_LEFT`/`TURN_RIGHT` 매핑을 서로 바꾸거나 카메라 장착 방향을 바로잡습니다.

## 3. 비전만 시험

```bash
python3 umbrella_follower.py
```

화면에 거리, 방위각과 `FORWARD`, `BACKWARD`, `TURN_LEFT`, `TURN_RIGHT`, `HOLD`,
`LOST` 상태가 표시됩니다. `q`로 종료합니다.

기본 탐지기는 Jetson에 설치된 NVIDIA VPI AprilTag이며 PVA 가속을 우선 사용합니다.
시작할 때 정사각형 태그 자체검사를 통과하지 못하면 VPI/CPU를 시도하고, VPI 자체를 초기화할 수 없을 때만 OpenCV로
자동 전환합니다. OpenCV fallback은 원본 탐지를 매 프레임 실행하고 CLAHE 및 다중 스케일
복구 탐지는 `detector.recovery_retry_interval_frames` 간격으로 실행합니다.

VPI 네이티브 모듈을 다시 빌드해야 할 때는 `./build_vpi_apriltag.sh`를 실행합니다.

## 4. phorce 연결

phorce는 임의 관절 명령 대신 로봇에 적재된 모션 ID(1~50)를 하나씩 재생합니다.
짧고 저속인 전진/후진/제자리 회전/정지 모션을 준비한 뒤 `config.json`의 각 상태에
ID를 입력합니다. `phorce list`로 실제 적재 슬롯을 확인할 수 있습니다.

물리 E-Stop을 손에 두고 로봇을 받침대에 띄운 상태에서 먼저 시험합니다.

```bash
phorce doctor
python3 umbrella_follower.py --enable-motion
```

`LOST`와 `HOLD`에는 안전한 정지/자세 유지 모션을 지정하세요. phorce의 `cancel()`은
E-Stop이 아니며 이미 시작한 모션이 즉시 멈춘다는 보장이 없습니다. 그래서 추종용 모션은
짧게 설계해야 합니다.

## 현재 컴퓨터 점검 결과

OpenCV 4.5.4의 AprilTag 사전과 phorce 0.1.0은 설치돼 있습니다. 점검 시점에는
`/dev/video*` 장치가 보이지 않았으므로, 실행 전에 웹캠 연결과 장치 권한을 확인하세요.
