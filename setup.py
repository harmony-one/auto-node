import subprocess
from setuptools import setup

version = subprocess.check_output('git rev-list --count HEAD', shell=True).decode()
commit = subprocess.check_output('git describe --always --long --dirty', shell=True).decode()

setup(
    name='AutoNode',
    version=f"v{version}.{commit}",
    description="AutoNode Python Library (this library is only used inside the sentry docker image)",
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
