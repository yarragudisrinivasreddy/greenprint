# Contributing to GreenPrint

Welcome! Here are the setup and validation guidelines for the GreenPrint Carbon platform.

## Developer Setup

1. **Clone and Navigate**:
   ```bash
   cd greenprint
   ```

2. **Set up Environment**:
   We recommend creating a Python 3.11 virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

3. **Install Dependencies**:
   Install runtime and development dependencies:
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

## Local Development Server

Start the Flask application factory:
```bash
python main.py
```
Open `http://localhost:8080` in your browser.

## Validation Gates

All code changes must satisfy three quality gates:

1. **Unit Tests (pytest)**:
   Verify all tests pass with code coverage:
   ```bash
   python -m pytest --cov=app --cov-fail-under=95
   ```

2. **Linting (pylint)**:
   Verify codebase maintains a score $\ge$ 9.9:
   ```bash
   pylint app/ main.py --fail-under=9.9
   ```

3. **Complexity (radon)**:
   Verify cyclomatic complexity does not exceed B(6):
   ```bash
   radon cc app/ -n B
   ```
