from setuptools import setup

setup(
    name='mono_openvins_tools', version='0.1.0',
    packages=['mono_openvins_tools'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/mono_openvins_tools']),
        ('share/mono_openvins_tools', ['package.xml']),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='user', maintainer_email='user@example.invalid',
    description='Historical mono image and IMU replay for OpenVINS', license='Apache-2.0',
    entry_points={'console_scripts': [
        'dataset = mono_openvins_tools.dataset:main',
        'replay = mono_openvins_tools.replay:main',
        'record_odometry = mono_openvins_tools.record:main',
        'px4_bridge = mono_openvins_tools.px4_bridge:main',
    ]},
)
