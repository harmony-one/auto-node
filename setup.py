import subprocess
from setuptools import setup

# TODO: single setup script using pypi...

setup(
    name='AutoNode',
    version=f"0.0.9",
    description="AutoNode Python Library",
    author='Daniel Van Der Maden',
    author_email='daniel@harmony.one',
    url="http://harmony.one/auto-node",
    packages=['AutoNode'],
    install_requires=[
        'requests',
        'pexpect',
        'pyhmy',
    ]
)
