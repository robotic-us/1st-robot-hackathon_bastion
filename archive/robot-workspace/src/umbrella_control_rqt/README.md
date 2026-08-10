# PhORCE 양산 rqt

퀵가이드의 `phorce_monitor`, `motion_action_server`와 양산 rqt 화면을 한 번에 실행합니다.
로봇 전원과 `eno1` 케이블을 먼저 확인하고 실행하세요.

```bash
cd /home/phorce/bastion_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select umbrella_control_rqt
source install/setup.bash
ros2 launch umbrella_control_rqt umbrella_system.launch.py
```

다음 실행부터는 마지막 두 줄만 사용하면 됩니다. 다른 NIC나 domain을 쓰려면
`nic:=eno1 domain_id:=21` launch 인자를 바꾸세요.

양산 모션 슬롯은 `config/umbrella_motions.json`에서 의도적으로 전부 `null`입니다.
현재는 GUI의 테스트 버튼 Motion 1, 2, 3만 실제 로봇에서 실행됩니다.
