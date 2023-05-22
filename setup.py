import subprocess
from setuptools import setup

setup(
    name='AutoNode',
    version=f"1.0.5",
    description="AutoNode Python Library",
    author='Daniel Van Der Maden',
    author_email='daniel@harmony.one',
    url="http://harmony.one/auto-node",
    packages=['AutoNode'],
    install_requires=[
        'requests==2.31.0',
        'pexpect==4.8.0',
        'cryptography==2.9.2',
        'pyhmy==20.5.20',
    ]
)
