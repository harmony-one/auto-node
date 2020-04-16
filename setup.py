import subprocess
from setuptools import setup


setup(
    name='AutoNode',
    version=f"v{subprocess.check_output('git rev-list --count HEAD', shell=True).decode()}",
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
