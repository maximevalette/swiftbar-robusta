# Contributing to SwiftBar Robusta Plugin

First off, thank you for considering contributing to the SwiftBar Robusta Plugin! It's people like you that make this tool better for everyone.

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please be respectful and considerate in all interactions.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples**
- **Include your configuration** (sanitized of sensitive data)
- **Include SwiftBar and macOS versions**
- **Include any error messages or logs**

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

- **Use a clear and descriptive title**
- **Provide a detailed description of the suggested enhancement**
- **Explain why this enhancement would be useful**
- **List any alternatives you've considered**

### Pull Requests

1. Fork the repo and create your branch from `main`
2. If you've added code that should be tested, add tests
3. Ensure the test suite passes
4. Make sure your code follows the existing style
5. Issue that pull request!

## Development Setup

1. Fork and clone the repository:
```bash
git clone https://github.com/yourusername/swiftbar-robusta.git
cd swiftbar-robusta
```

2. Install development dependencies:
```bash
uv pip install pytest pytest-mock pytest-cov ruff mypy
```

3. Create a test configuration:
```bash
cp example-config.yml ~/.config/swiftbar/robusta.yml
# Edit with your test credentials
```

4. Make your changes and test locally:
```bash
# Run the plugin
./robusta.5m.py

# Run tests
uv run pytest tests/ -v

# Run linting
uv run ruff check .
uv run mypy robusta.5m.py --ignore-missing-imports
```

## Testing

- Write tests for any new functionality
- Ensure all tests pass before submitting PR
- Aim for high test coverage
- Test with different configurations and edge cases

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=html

# Run specific test
uv run pytest tests/test_robusta.py::TestAlert::test_alert_creation
```

## Style Guide

### Python Style

- Follow PEP 8
- Use type hints where appropriate
- Keep functions focused and small
- Write descriptive variable names
- Add docstrings for classes and complex functions

### Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

Examples:
```
Add support for custom alert filtering

- Allow users to filter alerts by namespace
- Add regex pattern matching for alert names
- Update configuration schema

Fixes #123
```

### Code Organization

- Keep related functionality together
- Separate concerns (API, rendering, configuration)
- Use meaningful module and class names
- Document complex logic

## Release Process

1. Update version in `robusta.5m.py` header
2. Update CHANGELOG (if maintained)
3. Create a pull request with version bump
4. After merging, create a GitHub release
5. Tag the release with semantic versioning (e.g., v1.2.0)

## Questions?

Feel free to open an issue for any questions about contributing. We're here to help!

## Recognition

Contributors will be recognized in the README and release notes. Thank you for helping make this project better!