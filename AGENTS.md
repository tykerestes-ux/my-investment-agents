# AGENTS.md - Instructions for Autonomous Agents

This file provides guidance for AI agents working on the my-investment-agents repository.

## Project Overview

This repository contains investment-focused AI agents. The project is in its early stages of development.

## Development Environment

### Prerequisites

- Python 3.10+
- pip (Python package manager)

### Setup

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On Linux/macOS
# or
venv\Scripts\activate  # On Windows

# Install dependencies (when requirements.txt exists)
pip install -r requirements.txt
```

## Project Structure

```
my-investment-agents/
├── README.md           # Project documentation
├── AGENTS.md           # This file - agent instructions
├── requirements.txt    # Python dependencies (to be created)
├── src/                # Source code (to be created)
│   └── agents/         # Agent implementations
└── tests/              # Test files (to be created)
```

## Development Workflow

### Adding Dependencies

When adding new Python packages:
1. Install the package: `pip install <package-name>`
2. Update requirements: `pip freeze > requirements.txt`

### Code Style

- Follow PEP 8 style guidelines for Python code
- Use type hints for function signatures
- Write docstrings for all public functions and classes
- Keep functions focused and under 50 lines when possible

### Testing

```bash
# Run tests (when pytest is installed)
pytest tests/

# Run tests with coverage
pytest tests/ --cov=src
```

### Linting

```bash
# Run linter (when configured)
flake8 src/ tests/
# or
ruff check src/ tests/
```

## Conventions for Agents

### File Naming

- Use snake_case for Python files: `investment_agent.py`
- Use snake_case for test files: `test_investment_agent.py`
- Prefix test files with `test_`

### Code Organization

- Place all agent implementations in `src/agents/`
- Place utility functions in `src/utils/`
- Keep tests mirroring the source structure in `tests/`

### Commit Messages

- Use conventional commit format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore
- Keep messages concise but descriptive

### Before Submitting Changes

1. Ensure all tests pass
2. Run linting and fix any issues
3. Update documentation if adding new features
4. Check for sensitive data (API keys, credentials) - never commit these

## Important Notes

- This project may handle financial data - be mindful of data privacy
- Always validate external inputs
- Log errors appropriately but never log sensitive information
- When uncertain about implementation details, prefer explicit over implicit behavior
