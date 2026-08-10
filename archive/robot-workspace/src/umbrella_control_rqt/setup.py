from setuptools import find_packages, setup


package_name = "umbrella_control_rqt"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "plugin.xml"]),
        ("share/" + package_name + "/launch", ["launch/umbrella_system.launch.py"]),
        ("share/" + package_name + "/config", ["config/umbrella_motions.json"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="phorce",
    maintainer_email="phorce@example.com",
    description="PhORCE startup launch and rqt umbrella motion selector",
    license="Apache-2.0",
)
