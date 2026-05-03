.PHONY: install run clean

VENV_DIR = .venv

install:
	@echo "Synchronizing virtual environment and installing dependencies with uv..."
	uv sync

run:
	@echo "Running Flask application..."
	FLASK_APP=app.py uv run flask run

clean:
	@echo "Cleaning up virtual environment and build artifacts..."
	rm -rf $(VENV_DIR)
	rm -rf __pycache__
	rm -rf *.egg-info
	rm -rf build
