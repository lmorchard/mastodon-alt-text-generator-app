# Alt-Text Generator Flask Application

## Project Overview

This is a Flask web application designed to help with alt-text generation and Mastodon image management:

1.  **Local Image Alt-Text Generation:** Upload up to 5 images from your local machine. The app will use an OpenAI-compatible LLM to generate descriptive alt-text for each image.
2.  **Mastodon Alt-Text Management:** Connect to your Mastodon account via OAuth. You can then view your recent posts with images, identify images missing alt-text, generate alt-text using the LLM, and update the alt-text directly on Mastodon.

![screenshot 1](https://raw.githubusercontent.com/lmorchard/mastodon-alt-text-generator-app/refs/heads/main/Screenshot_20260621_125428.png)
![screenshot 2](https://raw.githubusercontent.com/lmorchard/mastodon-alt-text-generator-app/refs/heads/main/Screenshot_20260621_125450.png)

## Setup and Running Instructions

1.  **Navigate to the project directory:**
    The project files are in your workspace under `alt_text_generator_app_v3`.
    ```bash
    cd alt_text_generator_app_v3
    ```

2.  **Organize files:**
    Ensure your `templates` directory is set up correctly and contains `index.html` and `posts.html`.
    ```bash
    mkdir -p templates
    # Move index.html and posts.html if they are not already in the templates directory
    # (These were pulled to your workspace root in previous steps)
    mv ../index.html templates/
    mv ../posts.html templates/
    # Delete the old requirements.txt file, as we are now using pyproject.toml
    rm requirements.txt
    ```

3.  **Create a `.env` file:**
    Create a file named `.env` in the root of the `alt_text_generator_app_v3` directory. This file will store your environment variables. **Do not commit this file to version control**, as it contains sensitive credentials. The `.gitignore` file has already been updated to ignore it.

    Populate your `.env` file with the following, replacing the placeholder values with your actual keys and URLs:

    ```ini
    # .env (never commit this file)

    # Flask secret key for session management.
    # Generate a strong, random key, e.g., using `python -c 'import secrets; print(secrets.token_hex(32))'`
    FLASK_SECRET_KEY="YOUR_SUPER_SECRET_KEY_HERE"

    # OpenAI-compatible LLM configuration (e.g., LiteLLM proxy)
    OPENAI_API_KEY="sk-YOUR_OPENAI_OR_LITELLM_KEY"
    # Optional: if using a LiteLLM proxy or custom endpoint.
    # Omit OPENAI_BASE_URL to use the default OpenAI endpoint.
    OPENAI_BASE_URL="http://localhost:8000/v1"

    # Mastodon Integration Configuration
    # 1. Register an application on your Mastodon instance:
    #    Go to https://<YOUR_MASTODON_INSTANCE>/settings/applications/new
    #    - Application name: e.g., "Alt Text Generator"
    #    - Redirect URI: http://<YOUR_MACHINE_IP>:5000/mastodon/callback
    #    - Scopes: "read:statuses", "write:media"
    # 2. Get Client Key (ID) and Client Secret from the registered app.
    MASTODON_BASE_URL="https://<YOUR_MASTODON_INSTANCE>" # e.g., https://mastodon.social
    MASTODON_CLIENT_ID="YOUR_MASTODON_CLIENT_KEY"
    MASTODON_CLIENT_SECRET="YOUR_MASTODON_CLIENT_SECRET"

    # Optional: Flask app host and port. Defaults to 0.0.0.0:5000 if not set.
    HOST=0.0.0.0
    PORT=5000
    ```
    **Important Note for Mastodon Redirect URI**: When registering your Mastodon application, use your machine's actual IP address on your LAN (e.g., `http://192.168.1.100:5000/mastodon/callback`) instead of `127.0.0.1` if you intend to access it from other devices on your LAN. Make sure the `HOST` in your `.env` matches the IP used in the redirect URI if you're not using `0.0.0.0`.

4.  **Install dependencies and set up the virtual environment:**
    Use the `Makefile` target for this.
    ```bash
    make install
    ```
    This will create (if not present) and synchronize the `.venv` virtual environment with your `pyproject.toml` dependencies.

5.  **Run the Flask application:**
    Use the `Makefile` target for this. You can optionally override the `HOST` and `PORT` specified in the `.env` or defaults directly on the command line:
    ```bash
    make run                         # Uses HOST and PORT from .env or defaults (0.0.0.0:5000)
    HOST=127.0.0.1 make run          # Runs only on localhost
    PORT=8080 make run               # Runs on default host but on port 8080
    HOST=192.168.1.100 PORT=8000 make run # Runs on a specific IP and port
    ```
    This will set the `FLASK_APP` environment variable and then execute the `flask run` command within the correct environment using `uv run`.

6.  **Access the application:**
    Open your web browser and navigate to `http://<YOUR_MACHINE_IP_OR_HOST>:<PORT>` (e.g., `http://192.168.1.100:5000` or `http://localhost:5000`).

7.  **Clean up (optional):**
    To remove the virtual environment and build artifacts:
    ```bash
    make clean
    ```
