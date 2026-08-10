# Base movement motions

Motion tree의 첫 구간을 다음처럼 사용합니다.

- Motion 1: 직진 (`FORWARD_0_TO_360`)
- Motion 2: 좌회전 (`LEFT_LNEG_RPOS`)
- Motion 3: 우회전 (`RIGHT_LPOS_RNEG`)

네 휠은 `node 4/A = MD2/MD8`(왼쪽), `node 9/8 = MD7/MD6`(오른쪽)입니다.
직진은 모두 +360°로 끝납니다. 약 90° 선회를 위해 좌회전은 왼쪽 -309°/오른쪽
+309°, 우회전은 왼쪽 +309°/오른쪽 -309°로 끝나므로 회전 후에는 좌우 절대각도가
서로 다릅니다. ±270°에서 약 70°, ±347°에서 약 110°였던 베이스 회전 실측값을 보간한 값입니다.
따라서 이 세 모션은 기존 수렴형 motion tree의 다음 단계와 이어서 사용할 수 없습니다.

PCM 연결 후 GUI를 실행합니다.

```bash
cd /home/phorce/bastion_ws/motion_tree_gui
python3 motion_tree_gui.py --domain-id 21
```

CLI에서 개별 모션을 실행하려면 다음 중 하나만 실행합니다.

```bash
phorce play 1 --target robot --domain-id 21 --timeout 30
phorce play 2 --target robot --domain-id 21 --timeout 30
phorce play 3 --target robot --domain-id 21 --timeout 30
```

각 파일은 0° 시작 자세를 전제로 하므로 Motion 1~3 중 하나를 실행한 뒤 같은 시작
자세에서 다른 파일을 바로 연속 실행하면 안 됩니다.

## Route slots

- 4: `F F F`
- 5: `F F R F L F`
- 6: `F F R F F L F`
- 7: `F F R F F F L F`
- 8: `F F R F R F`
- 9: `F F R F F R F`
- 10: `F F R F F F R F`
- 14~20: 각각 4~10번의 역재생. 순서를 뒤집고 `F→B`, `L↔R`로 변환하며,
  대응 정방향 슬롯의 최종 액츄에이터 각도에서 시작해 0°로 복귀합니다.

여기서 `F`는 직진, `B`는 후진, `L`은 좌회전, `R`은 우회전입니다.

## Node 0x02 tilt slots

`node 0x02 = phact0 = MD0`만 명령하며 MD1~MD11은 모두 생략합니다.

- 21~24: 절대 0°에서 각각 +10°, +20°, +30°, +40°
- 25~28: 절대 0°에서 각각 -10°, -20°, -30°, -40°
- 31~34: 각각 +10°, +20°, +30°, +40°에서 절대 0°로 복귀
- 35~38: 각각 -10°, -20°, -30°, -40°에서 절대 0°로 복귀

기울기 속도는 10°당 1000ms이며 시작 정렬 300ms, 도달 후 유지 1000ms입니다.

## Node 0x03 tilt slots

`node 0x03 = phact1 = MD1`만 명령하며 다른 모든 축은 생략합니다.

- 41~45: 절대 0°에서 각각 +50°, +100°, +150°, +200°, +250°
- 46~50: 각각 +50°, +100°, +150°, +200°, +250°에서 절대 0°로 복귀

41~50번은 50°당 2500ms입니다. 모든 모션은 시작 정렬 300ms, 도달 후 유지
1000ms입니다.
