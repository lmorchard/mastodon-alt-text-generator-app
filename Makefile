.PHONY: install run clean

VENV_DIR = .venv
HOST ?= 0.0.0.0
PORT ?= 5000

install:
	@echo "Synchronizing virtual environment and installing dependencies with uv..."
	uv venv
	uv sync

run:
	@echo "Running Flask application on $(HOST):$(PORT)..."
	FLASK_APP=app.py uv run flask run --host $(HOST) --port $(PORT)

clean:
	@echo "Cleaning up virtual environment and build artifacts..."
	rm -rf $(VENV_DIR)
	rm -rf __pycache__
	rm -rf *.egg-info
	rm -rf build
