P-Vector 10-degree motion
=========================

Ready-made file
---------------
Motions/motion_04.csv

Motion definition
-----------------
- Motion slot / MS ID: 4
- Motion name: ROTATE10_DUAL
- Controlled motors: MD0 / phact0 / node 0x02 and MD1 / phact1 / node 0x03
- MD0 P0/P1/P2: absolute 0.0 deg -> 10.0 deg -> hold 10.0 deg
- MD1 P0/P1/P2: absolute 0.0 deg -> 10.0 deg -> hold 10.0 deg
- Acceleration/deceleration parameters: 0, 0
- Both controlled motors use the same P0/P1/P2 sequence.
- All other motors: not commanded ('-')

Important
---------
The first P-Vector value yd is an ABSOLUTE output-shaft angle relative to the
neutral posture, not a relative displacement. Therefore, to rotate +10 degrees
from a current absolute angle q, use target yd = q + 10.

Example generator commands
--------------------------
1) MD0 and MD1: 0 deg -> +10 deg
   python tools/make_10deg_motion.py --output motion_04.csv

2) MD1: 25 deg -> 35 deg
   python tools/make_10deg_motion.py --output motion_04.csv --motor 1 --start 25 --delta 10

3) MD0 only: 0 deg -> -10 deg in 2 seconds
   python tools/make_10deg_motion.py --output motion_04.csv --motor 0 --delta -10 --move-ms 2000

The .memo.json files in the uploaded examples contain robot-specific zero
snapshots. They are intentionally not generated here. Import/save the CSV in
the motion software so that the software can create metadata for the connected
robot, if required.
