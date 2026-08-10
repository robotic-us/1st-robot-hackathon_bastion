from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    domain_id = LaunchConfiguration("domain_id")
    nic = LaunchConfiguration("nic")
    return LaunchDescription([
        DeclareLaunchArgument("domain_id", default_value="21"),
        DeclareLaunchArgument("nic", default_value="eno1"),
        SetEnvironmentVariable("ROS_DOMAIN_ID", domain_id),
        Node(
            package="agx_phorce_bridge",
            executable="phorce_monitor",
            name="phorce_monitor",
            output="screen",
            parameters=[{"nic": nic, "mode": "op_idle", "axes": "auto", "mbx_enabled": True}],
        ),
        TimerAction(period=1.0, actions=[Node(
            package="agx_motion_slot",
            executable="motion_action_server",
            name="motion_action_server",
            output="screen",
            parameters=[{"backend": "ecat"}],
        )]),
        TimerAction(period=2.0, actions=[Node(
            package="rqt_gui",
            executable="rqt_gui",
            name="umbrella_rqt",
            output="screen",
            arguments=["--standalone", "umbrella_control_rqt.plugin.UmbrellaControlPlugin"],
        )]),
    ])
