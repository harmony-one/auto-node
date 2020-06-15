import subprocess
from setuptools import setup

setup(
    name='AutoNode',
    version=f"0.4.1",
    description="AutoNode Python Library",
    author='Daniel Van Der Maden',
    author_email='daniel@harmony.one',
    url="http://harmony.one/auto-node",
    packages=['AutoNode'],
    install_requires=[
        'requests==2.23.0',
        'pexpect==4.8.0',
        'cryptography==2.9.2',
        'pyhmy',
    ]
)
