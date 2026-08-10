# 태양 고도 기반 모션 선택기

대전의 현재 시각과 좌표로 태양 고도를 근사 계산한 뒤, `config.json`의 고도 구간에
해당하는 motion slot을 선택합니다. 외부 Python 패키지는 필요하지 않습니다.

기본 실행은 로봇을 움직이지 않는 dry-run입니다.

```bash
python3 sun_motion_selector.py
```

특정 시각으로 선택 결과를 시험할 수도 있습니다.

```bash
python3 sun_motion_selector.py --at 2026-08-07T14:30:00
```

선택된 모션을 실제로 실행하려면 로봇에 CSV가 해당 slot ID로 적재되어 있어야 하며,
`phorce` 환경에서 다음처럼 명시적으로 실행합니다.

```bash
python3 sun_motion_selector.py --enable-motion
```

아직 만들지 않은 모션은 `config.json`에서 `motion_id`와 `motion_file`을 `null`로 두면
선택 결과는 출력하지만 실행은 건너뜁니다. 고도 경계와 motion ID는 임시 값이므로 실제
기구의 각도 범위에 맞춰 조정해야 합니다.
