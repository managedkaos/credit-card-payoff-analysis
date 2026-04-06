APP = $(notdir $(CURDIR))
TAG = $(shell echo "$$(date +%F)-$$(git rev-parse --short HEAD)")

help:
	@echo "Run make <target> where target is one of the following..."
	@echo
	@echo "  all                      - run requirements, lint, test, and build"
	@echo "  requirements             - install runtime dependencies"
	@echo "  development-requirements - install development dependencies"
	@echo "  pre-commit-install       - install pre-commit hooks"
	@echo "  pre-commit-update        - update pre-commit hooks"
	@echo "  pre-commit-run           - run pre-commit on all files"
	@echo "  pre-commit-clean         - remove pre-commit hooks"
	@echo "  lint                     - run flake8, pylint, black, and isort checks"
	@echo "  black                    - format code with black"
	@echo "  isort                    - sort imports with isort"
	@echo "  test                     - run unit tests"
	@echo "  build                    - build docker container"
	@echo "  clean                    - clean up workspace and containers"

all: requirements lint test build

requirements:
	pip install --quiet --upgrade --requirement requirements.txt

development-requirements: requirements
	pip install --quiet --upgrade --requirement development-requirements.txt

pre-commit-install: development-requirements
	pre-commit install
	detect-secrets scan > .secrets.baseline

pre-commit-update: development-requirements
	pre-commit autoupdate
	$(MAKE) pre-commit-run

pre-commit-run: development-requirements
	pre-commit run --all-files

x_pre-commit-clean:
	pre-commit uninstall

lint:
	flake8 --ignore=E501,E231 *.py
	pylint --errors-only --disable=C0301 *.py
	black --diff *.py
	isort --check-only --diff *.py

fmt: black isort

black:
	black *.py

isort:
	isort *.py

test:
	python -m unittest --verbose --failfast

build: lint test
	docker build --tag $(APP):$(TAG) .

clean:
	docker container stop $(APP) || true
	docker container rm $(APP) || true
	@rm -rf ./__pycache__ ./tests/__pycache__ .ruff_cache
	@rm -f .*~ *.pyc

.PHONY: help requirements lint black isort test build clean development-requirements pre-commit-install pre-commit-run pre-commit-clean
