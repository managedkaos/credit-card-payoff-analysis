# python-container-template

A template repo for container-ized Python applications.

## Development Setup

This template includes pre-commit hooks for code quality and security checks. To set up the development environment:

1. Install development dependencies:

   ```bash
   make development-requirements
   ```

2. Install pre-commit hooks:

   ```bash
   make pre-commit-install
   ```

3. Run pre-commit on all files (optional):

   ```bash
   make pre-commit-run
   ```

## Pre-commit Hooks

The following hooks are configured to run automatically on commit:

- **Black**: Code formatting with consistent style
- **isort**: Import sorting and organization
- **flake8**: Linting for code quality
- **bandit**: Security vulnerability scanning
- **detect-secrets**: Secret detection in code
- **Various checks includings**:
  - Merge conflict detection
  - YAML/JSON validation
  - Large file detection
  - Trailing whitespace removal
  - End-of-file fixes

## Available Make Targets

- `make development-requirements` - Install development dependencies
- `make pre-commit-install` - Install pre-commit hooks
- `make pre-commit-run` - Run pre-commit on all files
- `make pre-commit-clean` - Remove pre-commit hooks
- `make lint` - Run linting tools manually
- `make fmt` - Format code with black and isort
