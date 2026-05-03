import os
import base64
from dotenv import load_dotenv

load_dotenv()
import requests as http_requests
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import openai
from mastodon import Mastodon

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-in-production')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_openai_client():
    return openai.OpenAI(
        api_key=os.environ.get('OPENAI_API_KEY'),
        base_url=os.environ.get('OPENAI_BASE_URL'),
    )


def generate_alt_text(client, image_data_b64, media_type):
    response = client.chat.completions.create(
        model=os.environ.get('ALT_TEXT_LLM_MODEL', 'gpt-4o-mini'),
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:{media_type};base64,{image_data_b64}',
                        },
                    },
                    {
                        'type': 'text',
                        'text': (
                            'Generate concise, descriptive alt text for this image. '
                            'Focus on the key visual elements and purpose of the image. '
                            'Keep it under 125 characters when possible.'
                        ),
                    },
                ],
            }
        ],
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def get_mastodon_client(access_token=None):
    base_url = os.environ.get('MASTODON_BASE_URL')
    client_id = os.environ.get('MASTODON_CLIENT_ID')
    client_secret = os.environ.get('MASTODON_CLIENT_SECRET')

    if not all([base_url, client_id, client_secret]):
        return None

    return Mastodon(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        api_base_url=base_url,
    )


def mastodon_configured():
    return all([
        os.environ.get('MASTODON_BASE_URL'),
        os.environ.get('MASTODON_CLIENT_ID'),
        os.environ.get('MASTODON_CLIENT_SECRET'),
    ])


# ---------------------------------------------------------------------------
# Local upload routes
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template(
            'index.html',
            mastodon_configured=mastodon_configured(),
            mastodon_username=session.get('mastodon_username'),
            mastodon_display_name=session.get('mastodon_display_name'),
        )

    results = []
    files = request.files.getlist('images[]')
    client = get_openai_client()

    for file in files[:MAX_IMAGES]:
        if not file or not file.filename:
            continue

        if not allowed_file(file.filename):
            results.append({
                'filename': file.filename,
                'error': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}',
            })
            continue

        try:
            image_data = file.read()
            image_data_b64 = base64.b64encode(image_data).decode('utf-8')
            media_type = file.mimetype or 'image/jpeg'
            preview_url = f'data:{media_type};base64,{image_data_b64}'
            alt_text = generate_alt_text(client, image_data_b64, media_type)
            results.append({
                'filename': file.filename,
                'preview_url': preview_url,
                'alt_text': alt_text,
            })
        except Exception as e:
            results.append({
                'filename': file.filename,
                'error': str(e),
            })

    return render_template(
        'index.html',
        results=results,
        mastodon_configured=mastodon_configured(),
        mastodon_username=session.get('mastodon_username'),
        mastodon_display_name=session.get('mastodon_display_name'),
    )


# ---------------------------------------------------------------------------
# Mastodon OAuth routes
# ---------------------------------------------------------------------------

@app.route('/mastodon/login')
def mastodon_login():
    if not mastodon_configured():
        flash(
            'Mastodon is not configured. Set MASTODON_CLIENT_ID, '
            'MASTODON_CLIENT_SECRET, and MASTODON_BASE_URL.',
            'error',
        )
        return redirect(url_for('index'))

    mastodon = get_mastodon_client()
    redirect_uri = url_for('mastodon_callback', _external=True)
    try:
        auth_url = mastodon.auth_request_url(
            redirect_uris=redirect_uri,
            scopes=['read:statuses', 'write:media', 'write:statuses', 'read:accounts'],
        )
    except Exception as e:
        flash(f'Could not build Mastodon login URL: {e}', 'error')
        return redirect(url_for('index'))

    return redirect(auth_url)


@app.route('/mastodon/callback')
def mastodon_callback():
    code = request.args.get('code')
    if not code:
        flash('Mastodon login failed: no authorization code received.', 'error')
        return redirect(url_for('index'))

    if not mastodon_configured():
        flash('Mastodon is not configured.', 'error')
        return redirect(url_for('index'))

    mastodon = get_mastodon_client()
    redirect_uri = url_for('mastodon_callback', _external=True)
    try:
        access_token = mastodon.log_in(
            code=code,
            redirect_uri=redirect_uri,
            scopes=['read:statuses', 'write:media', 'write:statuses', 'read:accounts'],
        )
        authed = get_mastodon_client(access_token)
        account = authed.me()
        session['mastodon_access_token'] = access_token
        session['mastodon_username'] = account['username']
        session['mastodon_display_name'] = account.get('display_name') or account['username']
        flash(f'Logged in as @{account["username"]}', 'success')
    except Exception as e:
        flash(f'Mastodon login failed: {e}', 'error')

    return redirect(url_for('index'))


@app.route('/mastodon/logout')
def mastodon_logout():
    session.pop('mastodon_access_token', None)
    session.pop('mastodon_username', None)
    session.pop('mastodon_display_name', None)
    flash('Logged out from Mastodon.', 'info')
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Posts route
# ---------------------------------------------------------------------------

@app.route('/posts')
def posts():
    access_token = session.get('mastodon_access_token')
    if not access_token:
        flash('Please log in with Mastodon first.', 'error')
        return redirect(url_for('index'))

    try:
        mastodon = get_mastodon_client(access_token)
        account = mastodon.me()
        statuses = mastodon.account_statuses(account['id'], limit=40)
    except Exception as e:
        flash(f'Failed to fetch posts: {e}', 'error')
        return redirect(url_for('index'))

    posts_with_media = []
    for status in statuses:
        media = status.get('media_attachments', [])
        images = [m for m in media if m['type'] in ('image', 'gifv')]
        if not images:
            continue
        posts_with_media.append({
            'id': status['id'],
            'url': status['url'],
            'content': status['content'],
            'created_at': status['created_at'],
            'images': [
                {
                    'id': img['id'],
                    'url': img['url'],
                    'preview_url': img.get('preview_url') or img['url'],
                    'alt_text': img.get('description') or '',
                    'missing_alt': not img.get('description'),
                }
                for img in images
            ],
        })

    return render_template(
        'posts.html',
        posts=posts_with_media,
        username=session.get('mastodon_username'),
        display_name=session.get('mastodon_display_name'),
    )


# ---------------------------------------------------------------------------
# API endpoints (JSON) for alt-text generation and Mastodon update
# ---------------------------------------------------------------------------

@app.route('/api/generate-alt-text', methods=['POST'])
def api_generate_alt_text():
    if not session.get('mastodon_access_token'):
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(silent=True) or {}
    image_url = data.get('image_url')
    if not image_url:
        return jsonify({'error': 'No image_url provided'}), 400

    try:
        resp = http_requests.get(image_url, timeout=15)
        resp.raise_for_status()
        media_type = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
        image_data_b64 = base64.b64encode(resp.content).decode('utf-8')
        client = get_openai_client()
        alt_text = generate_alt_text(client, image_data_b64, media_type)
        return jsonify({'alt_text': alt_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-alt-text', methods=['POST'])
def api_update_alt_text():
    access_token = session.get('mastodon_access_token')
    if not access_token:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(silent=True) or {}
    media_id = data.get('media_id')
    alt_text = (data.get('alt_text') or '').strip()

    if not media_id:
        return jsonify({'error': 'No media_id provided'}), 400

    try:
        mastodon = get_mastodon_client(access_token)
        mastodon.media_update(media_id, description=alt_text)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
