import os
import base64
from flask import Flask, render_template, request
import openai

app = Flask(__name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGES = 5


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_openai_client():
    return openai.OpenAI(
        api_key=os.environ.get('OPENAI_API_KEY'),
        base_url=os.environ.get('OPENAI_BASE_URL'),
    )


def generate_alt_text(client, image_data_b64, media_type):
    response = client.chat.completions.create(
        model='gpt-4o-mini',
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


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('index.html')

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

    return render_template('index.html', results=results)


if __name__ == '__main__':
    app.run(debug=True)
