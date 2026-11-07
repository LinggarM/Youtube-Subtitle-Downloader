from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
from datetime import datetime, timezone
import re
import os
import requests
import json
import sqlite3
import time
from contextlib import contextmanager

app = Flask(__name__)
HISTORY_DATABASE = os.path.join(app.instance_path, 'history.sqlite3')
HISTORY_FIELDS = ('id', 'title', 'videoId', 'url', 'language', 'transcript', 'keyPoints', 'createdAt', 'updatedAt')


def get_history_connection():
    """Open the persistent local history database and ensure its schema exists."""
    os.makedirs(app.instance_path, exist_ok=True)
    connection = sqlite3.connect(HISTORY_DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            video_id TEXT NOT NULL,
            url TEXT NOT NULL,
            language TEXT NOT NULL,
            transcript TEXT NOT NULL,
            key_points TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS history_imports (
            token TEXT PRIMARY KEY,
            imported_at TEXT NOT NULL
        )
    ''')
    return connection


@contextmanager
def history_connection():
    connection = get_history_connection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def validate_history_entry(entry):
    """Validate a history record received from the browser."""
    if not isinstance(entry, dict):
        return None
    if any(not isinstance(entry.get(field, ''), str) for field in HISTORY_FIELDS):
        return None
    if not entry.get('id', '').strip() or not entry.get('transcript', '').strip():
        return None
    now = datetime.now(timezone.utc).isoformat()
    return {
        'id': entry['id'].strip(),
        'title': entry.get('title', '').strip() or 'Untitled video',
        'video_id': entry.get('videoId', '').strip(),
        'url': entry.get('url', '').strip(),
        'language': entry.get('language', '').strip(),
        'transcript': entry['transcript'],
        'key_points': entry.get('keyPoints', ''),
        'created_at': entry.get('createdAt', '').strip() or now,
        'updated_at': entry.get('updatedAt', '').strip() or now
    }


def insert_history_entry(connection, entry, ignore_existing=False):
    conflict_clause = 'DO NOTHING' if ignore_existing else '''
        DO UPDATE SET
            title = excluded.title,
            video_id = excluded.video_id,
            url = excluded.url,
            language = excluded.language,
            transcript = excluded.transcript,
            key_points = excluded.key_points,
            updated_at = excluded.updated_at
    '''
    connection.execute(f'''
        INSERT INTO history (
            id, title, video_id, url, language, transcript, key_points, created_at, updated_at
        ) VALUES (
            :id, :title, :video_id, :url, :language, :transcript, :key_points, :created_at, :updated_at
        )
        ON CONFLICT(id) {conflict_clause}
    ''', entry)


def serialize_history_entry(row):
    return {
        'id': row['id'],
        'title': row['title'],
        'videoId': row['video_id'],
        'url': row['url'],
        'language': row['language'],
        'transcript': row['transcript'],
        'keyPoints': row['key_points'],
        'createdAt': row['created_at'],
        'updatedAt': row['updated_at']
    }

# AI API configuration
load_dotenv()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_AI_STUDIO_API_KEY = os.getenv("GOOGLE_AI_STUDIO_API_KEY")
GOOGLE_AI_STUDIO_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
SUBMISSION_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'submissions.log')

def get_video_title(video_id):
    """Get the title of a YouTube video using its oEmbed endpoint"""
    response = requests.get(
        "https://www.youtube.com/oembed",
        params={
            'url': f"https://www.youtube.com/watch?v={video_id}",
            'format': 'json'
        },
        timeout=10
    )
    response.raise_for_status()
    response_data = response.json()
    if not isinstance(response_data, dict):
        return None
    title = response_data.get('title')
    return title.strip() if isinstance(title, str) and title.strip() else None

def log_submission(url, video_id, video_title):
    """Append a successful transcript extraction to the submission log"""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'url': url,
        'video_id': video_id,
        'title': video_title
    }
    with open(SUBMISSION_LOG, 'a', encoding='utf-8') as log_file:
        log_file.write(json.dumps(entry, ensure_ascii=False) + '\n')

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:watch\?v=)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_available_languages(video_id):
    """Get list of available subtitle languages"""
    try:
        ytt_api = YouTubeTranscriptApi()
        list_transcript = ytt_api.list(video_id)
        languages = []
        for transcript in list_transcript:
            languages.append({
                'language_code': transcript.language_code,
                'language': transcript.language,
                'is_generated': transcript.is_generated,
                'is_translatable': transcript.is_translatable
            })
        return languages
    except Exception as e:
        return None

def get_transcript_text(video_id, language_code='en'):
    """Get transcript text from video ID with specified language"""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language_code])
        subtitle = ''
        for index, value in enumerate(transcript):
            if index == 0:
                subtitle = subtitle + (value['text'])
            else:
                subtitle = subtitle + ' ' + (value['text'])
        return subtitle
    except Exception as e:
        # Try without language specification if specific language fails
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            subtitle = ''
            for index, value in enumerate(transcript):
                if index == 0:
                    subtitle = subtitle + (value['text'])
                else:
                    subtitle = subtitle + ' ' + (value['text'])
            return subtitle
        except Exception as e2:
            return None


class AIAPIError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code

def _call_ai_api(provider, model, prompt):
    """Helper function untuk melakukan request ke AI API (Groq/Google)"""
    try:
        if provider == 'groq':
            response = requests.post(
                GROQ_API_URL,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=30
            )
        else:
            response = requests.post(
                f"{GOOGLE_AI_STUDIO_API_URL}/{model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": GOOGLE_AI_STUDIO_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=(10, 120)
            )
        response.raise_for_status()
        response_data = response.json()
        
        if provider == 'groq':
            choices = response_data.get('choices') if isinstance(response_data, dict) else None
            message = choices[0].get('message') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            result = message.get('content') if isinstance(message, dict) else None
        else:
            candidates = response_data.get('candidates') if isinstance(response_data, dict) else None
            candidate_content = candidates[0].get('content') if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict) else None
            parts = candidate_content.get('parts') if isinstance(candidate_content, dict) else None
            result = '\n'.join(part['text'] for part in parts if isinstance(part, dict) and isinstance(part.get('text'), str)) if isinstance(parts, list) else None
            
        if not isinstance(result, str):
            raise AIAPIError(502, f'{provider} returned an unexpected response format.')
        return result
        
    except requests.exceptions.HTTPError as e:
        response = e.response
        try:
            error_data = response.json()
        except ValueError:
            error_message = response.text.strip() or str(e)
        else:
            api_error = error_data.get('error') if isinstance(error_data, dict) else None
            error_message = api_error.get('message') if isinstance(api_error, dict) else str(api_error or e)
        raise AIAPIError(response.status_code, error_message) from e

# Ganti fungsi get_key_points dengan versi yang mendukung pilihan chunking:
def get_key_points(transcript, provider, model, target_language="Indonesia", use_chunking=True):
    """Get key points dengan opsi chunking universal."""
    
    # Jika user memilih chunking DAN transkrip cukup panjang (>6000 karakter)
    if use_chunking and len(transcript) > 6000:
        chunk_size = 6000
        chunks = [transcript[i:i+chunk_size] for i in range(0, len(transcript), chunk_size)]
        chunk_summaries = []
        
        for i, chunk in enumerate(chunks):
            prompt = f"Bagian {i+1} dari {len(chunks)}. Berikan poin-poin penting dari transkrip berikut dalam bahasa {target_language}:\n\n{chunk}"
            result = _call_ai_api(provider, model, prompt)
            chunk_summaries.append(result)
            time.sleep(0.5) # Jeda agar tidak terkena rate limit
            
        # Gabungkan hasil chunk
        combined_text = "\n\n---\n\n".join(chunk_summaries)
        final_prompt = (
            f"Gabungkan dan ringkas semua poin-poin penting berikut menjadi satu ringkasan utuh "
            f"yang terstruktur, padat, dan tidak berulang, dalam bahasa {target_language}:\n\n{combined_text}"
        )
        return _call_ai_api(provider, model, final_prompt)
    
    # Jika user TIDAK memilih chunking, atau transkrip pendek, kirim langsung (perilaku asli)
    else:
        prompt = f"Berikan poin-poin penting dari transkrip berikut dalam bahasa {target_language}:\n\n{transcript}"
        return _call_ai_api(provider, model, prompt)

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/history')
def history():
    """Render the browser-local transcript history page"""
    return render_template('history.html')

@app.route('/api/languages', methods=['POST'])
def get_languages():
    """API endpoint to get available subtitle languages"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Extract video ID from URL
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        # Get available languages
        languages = get_available_languages(video_id)
        if languages is None:
            return jsonify({'error': 'Could not retrieve available languages. Video may not have subtitles or may be private.'}), 404
        
        return jsonify({
            'video_id': video_id,
            'languages': languages,
            'success': True
        })
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/api/history', methods=['GET', 'POST'])
def manage_history():
    """List or save history records in SQLite."""
    if request.method == 'GET':
        try:
            page = max(1, int(request.args.get('page', '1')))
            per_page = int(request.args.get('per_page', '10'))
        except ValueError:
            return jsonify({'error': 'Page and page size must be integers.'}), 400
        if per_page not in (10, 20, 50):
            return jsonify({'error': 'Page size must be 10, 20, or 50.'}), 400

        search = request.args.get('q', '').strip()
        language = request.args.get('language', '').strip()
        status = request.args.get('status', 'all')
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        if len(search) > 200 or len(language) > 100:
            return jsonify({'error': 'Search filters are too long.'}), 400
        if status not in ('all', 'with_keypoints', 'transcript_only'):
            return jsonify({'error': 'Invalid key points filter.'}), 400
        try:
            if date_from:
                datetime.strptime(date_from, '%Y-%m-%d')
            if date_to:
                datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Dates must use YYYY-MM-DD format.'}), 400
        if date_from and date_to and date_from > date_to:
            return jsonify({'error': 'Start date must not be later than end date.'}), 400

        conditions = []
        parameters = []
        if search:
            escaped_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            pattern = f'%{escaped_search}%'
            conditions.append(
                "(title LIKE ? ESCAPE '\\' OR video_id LIKE ? ESCAPE '\\' "
                "OR language LIKE ? ESCAPE '\\' OR transcript LIKE ? ESCAPE '\\' "
                "OR key_points LIKE ? ESCAPE '\\')"
            )
            parameters.extend([pattern] * 5)
        if language:
            escaped_language = language.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            conditions.append("language LIKE ? ESCAPE '\\'")
            parameters.append(f'%{escaped_language}%')
        if status == 'with_keypoints':
            conditions.append("length(trim(key_points)) > 0")
        elif status == 'transcript_only':
            conditions.append("length(trim(key_points)) = 0")
        if date_from:
            conditions.append("substr(created_at, 1, 10) >= ?")
            parameters.append(date_from)
        if date_to:
            conditions.append("substr(created_at, 1, 10) <= ?")
            parameters.append(date_to)
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ''
        offset = (page - 1) * per_page

        try:
            with history_connection() as connection:
                total = connection.execute(
                    f'SELECT COUNT(*) FROM history{where_clause}', parameters
                ).fetchone()[0]
                page_count = (total + per_page - 1) // per_page
                page = min(page, max(page_count, 1))
                rows = connection.execute(
                    f'SELECT * FROM history{where_clause} '
                    'ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?',
                    [*parameters, per_page, (page - 1) * per_page]
                ).fetchall()
            return jsonify({
                'history': [serialize_history_entry(row) for row in rows],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': page_count
                },
                'success': True
            })
        except (sqlite3.Error, OSError):
            app.logger.exception("Could not read local history database")
            return jsonify({'error': 'Could not read history from the SQLite database.'}), 500

    data = request.get_json(silent=True)
    entry = validate_history_entry(data)
    if entry is None:
        return jsonify({'error': 'A valid history record with an ID and transcript is required.'}), 400
    try:
        with history_connection() as connection:
            insert_history_entry(connection, entry)
        return jsonify({'success': True}), 201
    except (sqlite3.Error, OSError):
        app.logger.exception("Could not save local history")
        return jsonify({'error': 'Could not save history to the SQLite database.'}), 500


@app.route('/api/history/import', methods=['POST'])
def import_history():
    """Import a browser's legacy history once, preserving its local backup."""
    data = request.get_json(silent=True)
    token = data.get('token') if isinstance(data, dict) else None
    entries = data.get('history') if isinstance(data, dict) else None
    if not isinstance(token, str) or not token.strip() or not isinstance(entries, list):
        return jsonify({'error': 'A migration token and history list are required.'}), 400
    if len(entries) > 5000:
        return jsonify({'error': 'The history import is too large.'}), 413

    validated_entries = [validate_history_entry(entry) for entry in entries]
    if any(entry is None for entry in validated_entries):
        return jsonify({'error': 'One or more legacy history records have an invalid format.'}), 400

    try:
        with history_connection() as connection:
            cursor = connection.execute(
                'INSERT OR IGNORE INTO history_imports (token, imported_at) VALUES (?, ?)',
                (token.strip(), datetime.now(timezone.utc).isoformat())
            )
            if cursor.rowcount:
                for entry in validated_entries:
                    insert_history_entry(connection, entry, ignore_existing=True)
        return jsonify({'success': True}), 200
    except (sqlite3.Error, OSError):
        app.logger.exception("Could not import browser history")
        return jsonify({'error': 'Could not import browser history into SQLite.'}), 500


@app.route('/api/history/<entry_id>', methods=['PATCH', 'DELETE'])
def update_or_delete_history(entry_id):
    """Update key points or delete a history record."""
    try:
        with history_connection() as connection:
            if request.method == 'DELETE':
                cursor = connection.execute('DELETE FROM history WHERE id = ?', (entry_id,))
                if cursor.rowcount == 0:
                    return jsonify({'error': 'History entry not found.'}), 404
                return jsonify({'success': True})

            data = request.get_json(silent=True)
            key_points = data.get('keyPoints') if isinstance(data, dict) else None
            if not isinstance(key_points, str):
                return jsonify({'error': 'Key points must be a string.'}), 400
            cursor = connection.execute(
                'UPDATE history SET key_points = ?, updated_at = ? WHERE id = ?',
                (key_points, datetime.now(timezone.utc).isoformat(), entry_id)
            )
            if cursor.rowcount == 0:
                return jsonify({'error': 'History entry not found.'}), 404
        return jsonify({'success': True})
    except (sqlite3.Error, OSError):
        app.logger.exception("Could not update local history")
        return jsonify({'error': 'Could not update the SQLite history database.'}), 500

@app.route('/api/transcript', methods=['POST'])
def get_transcript():
    """API endpoint to get transcript from YouTube URL"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        language_code = data.get('language_code', 'en')
        video_title = data.get('video_title')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Extract video ID from URL
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        # Get transcript
        transcript = get_transcript_text(video_id, language_code)
        if transcript is None:
            return jsonify({'error': 'Could not retrieve transcript. Video may not have subtitles in the selected language or may be private.'}), 404

        if not isinstance(video_title, str) or not video_title.strip():
            try:
                video_title = get_video_title(video_id)
            except requests.exceptions.RequestException as e:
                app.logger.warning("Could not retrieve title for video %s: %s", video_id, e)
                video_title = None
        video_title = video_title.strip() if isinstance(video_title, str) and video_title.strip() else 'Unknown video title'
        log_submission(url, video_id, video_title)
        
        return jsonify({
            'video_id': video_id,
            'video_title': video_title,
            'transcript': transcript,
            'language_code': language_code,
            'success': True
        })
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/api/keypoints', methods=['POST'])
def get_keypoints():
    """API endpoint to get key points from transcript"""
    try:
        data = request.get_json()
        transcript = data.get('transcript', '').strip()
        provider = data.get('provider', 'groq')
        model = data.get('model', 'openai/gpt-oss-20b')
        target_language = data.get('target_language', 'Indonesia')
        use_chunking = data.get('use_chunking', False)
        
        if not transcript:
            return jsonify({'error': 'Transcript is required'}), 400
        
        allowed_models = {
            'groq': ['openai/gpt-oss-20b', 'openai/gpt-oss-120b'],
            'google': ['gemini-3.8-flash', 'gemini-3.1-pro-preview']
        }
        if provider not in allowed_models or model not in allowed_models[provider]:
            return jsonify({'error': 'Invalid model selected'}), 400

        api_key = GROQ_API_KEY if provider == 'groq' else GOOGLE_AI_STUDIO_API_KEY
        key_name = 'GROQ_API_KEY' if provider == 'groq' else 'GOOGLE_AI_STUDIO_API_KEY'
        if not api_key:
            return jsonify({'error': f'{key_name} is not configured. Add a valid API key to the .env file.'}), 503
        
        try:
            # <-- Teruskan parameter use_chunking ke fungsi
            key_points = get_key_points(transcript, provider, model, target_language, use_chunking)
        except AIAPIError as e:
            app.logger.error("%s API returned %s: %s", provider, e.status_code, e)
            return jsonify({'error': f'{provider} API error ({e.status_code}): {e}'}), 502
        except requests.exceptions.Timeout:
            app.logger.warning("%s API request timed out for model %s", provider, model)
            return jsonify({'error': f'{provider} API request timed out. Try again or choose a faster model.'}), 504
        except requests.exceptions.RequestException:
            app.logger.exception("Could not reach %s API", provider)
            return jsonify({'error': f'Could not reach {provider} API. Check your internet connection and try again.'}), 502
        
        return jsonify({
            'key_points': key_points,
            'provider': provider,
            'model': model,
            'success': True
        })
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # app.run(debug=True, host='0.0.0.0', port=5000)
    app.run()