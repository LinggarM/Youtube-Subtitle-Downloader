from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
from datetime import datetime, timezone
import re
import os
import requests
import json

app = Flask(__name__)

# Groq API configuration
load_dotenv()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
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


class GroqAPIError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def get_key_points(transcript, model="openai/gpt-oss-20b"):
    """Get key points from transcript using Groq API"""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        }
        
        content = f"beri poin penting: {transcript}"
        
        data = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        
        response = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        
        response_data = response.json()
        choices = response_data.get('choices') if isinstance(response_data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise GroqAPIError(502, 'Groq returned an unexpected response format.')
        message = choices[0].get('message') if isinstance(choices[0], dict) else None
        content = message.get('content') if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise GroqAPIError(502, 'Groq returned an unexpected response format.')
        return content
            
    except requests.exceptions.HTTPError as e:
        response = e.response
        try:
            error_data = response.json()
        except ValueError:
            error_message = response.text.strip() or str(e)
        else:
            api_error = error_data.get('error') if isinstance(error_data, dict) else None
            error_message = api_error.get('message') if isinstance(api_error, dict) else str(api_error or e)
        raise GroqAPIError(response.status_code, error_message) from e

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

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
        model = data.get('model', 'openai/gpt-oss-20b')
        
        if not transcript:
            return jsonify({'error': 'Transcript is required'}), 400
        
        # Validate model
        allowed_models = [
            'openai/gpt-oss-20b',
            'openai/gpt-oss-120b'
        ]
        if model not in allowed_models:
            return jsonify({'error': 'Invalid model selected'}), 400

        if not GROQ_API_KEY:
            return jsonify({'error': 'GROQ_API_KEY is not configured. Add a valid Groq API key to the .env file.'}), 503
        
        try:
            key_points = get_key_points(transcript, model)
        except GroqAPIError as e:
            app.logger.error("Groq API returned %s: %s", e.status_code, e)
            return jsonify({'error': f'Groq API error ({e.status_code}): {e}'}), 502
        except requests.exceptions.RequestException:
            app.logger.exception("Could not reach Groq API")
            return jsonify({'error': 'Could not reach Groq API. Check your internet connection and try again.'}), 502
        
        return jsonify({
            'key_points': key_points,
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