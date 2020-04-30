.PHONY: clean-build clean-py

help:
	@echo "clean-build - remove build artifacts"
	@echo "clean-py - remove Python file artifacts"
	@echo "install - install AutoNode locally"
	@echo "release - package and upload a release"
	@echo "sdist - package"

clean: clean-build clean-py

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info
	rm -fr .eggs/

clean-py:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

install:
	bash ./scripts/dev_install.sh

release: clean
	python3 setup.py sdist bdist_wheel
	twine upload dist/*

sdist: clean
	python3 setup.py sdist bdist_wheel
	ls -l dist
