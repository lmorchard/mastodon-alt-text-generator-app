.PHONY: install run clean

VENV_DIR = .venv

install:
	@echo "Synchronizing virtual environment and installing dependencies with uv..."
	uv venv
	uv sync

run:
	@echo "Running Flask application..."
	uv run FLASK_APP=app.py flask run

clean:
	@echo "Cleaning up virtual environment and build artifacts..."
	rm -rf $(VENV_DIR)
	rm -rf __pycache__
	rm -rf *.egg-info
	rm -rf build
