# PhORCE 6축 실시간 상대각 컨트롤러

모션 슬롯을 사용하지 않는다. `/phorce/feedback`의 현재 절대각을 상대 0도로
캡처하고, 상대 목표를 절대각으로 변환해 `/phorce_monitor/cmd`에 200 Hz로 보낸다.

운용 축과 6개 값의 순서는 `0, 1, 2, 6, 7, 8` (`0x01C7`)이다.

## 실행

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=21
python3 /home/phorce/bastion_ws/relative_angle/phorce_relative_controller.py
```

노드는 첫 정상 피드백 자세를 자동으로 0도로 잡고 HOLD를 계속 발행한다.

브리지의 command 모드를 arm/confirm한 다음 상대 목표 적용을 활성화한다.

```bash
ros2 service call /phorce_monitor/arm std_srvs/srv/Trigger '{}'
ros2 service call /phorce_monitor/confirm std_srvs/srv/Trigger '{}'
ros2 service call /phorce_relative/enable std_srvs/srv/Trigger '{}'
```

6축을 모두 상대 +30도로 보내려면:

```bash
ros2 topic pub --once /phorce_relative/target_deg \
  std_msgs/msg/Float64MultiArray "{data: [30, 30, 30, 30, 30, 30]}"
```

각 축을 서로 다르게 보내는 예:

```bash
ros2 topic pub --once /phorce_relative/target_deg \
  std_msgs/msg/Float64MultiArray "{data: [10, -10, 20, 0, 15, -5]}"
```

현재 자세를 새 상대 0도로 잡으려면 먼저 정지시킨 뒤 영점을 갱신한다.

```bash
ros2 service call /phorce_relative/disable std_srvs/srv/Trigger '{}'
ros2 service call /phorce_relative/set_zero std_srvs/srv/Trigger '{}'
```

기본 속도 제한은 축당 30 deg/s, 상대 목표 범위는 ±180도다. ROS 파라미터
`max_speed_deg_s`, `max_relative_deg`로 바꿀 수 있다.

## 현재 PCM 펌웨어 제약

이 컨트롤러는 상대각 계산과 실시간 `PhorceCommand` 스트리밍을 완성한다. 하지만
현재 PCM 펌웨어는 command relay의 기대 마스크를 `0x0002`로 고정하고 있고 제어
프레임 flush도 비활성화된 해커톤 P-Vector 전용 빌드다. 따라서 PCM 펌웨어에서
`CM_ECAT_EXPECTED_AXIS_MASK=0x01C7` 및 control-frame flush를 활성화하지 않으면
Jetson에서 명령이 정상 발행돼도 실제 6축에는 전달되지 않는다.
