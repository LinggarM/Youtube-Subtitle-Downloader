from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
import re
import os
import requests
import json

app = Flask(__name__)

# Groq API configuration
load_dotenv()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

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

def get_key_points(transcript, model="meta-llama/llama-4-scout-17b-16e-instruct"):
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
        
        response = requests.post(GROQ_API_URL, headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        
        response_data = response.json()
        if 'choices' in response_data and len(response_data['choices']) > 0:
            return response_data['choices'][0]['message']['content']
        else:
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

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
        
        return jsonify({
            'video_id': video_id,
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
        model = data.get('model', 'meta-llama/llama-4-scout-17b-16e-instruct')
        
        if not transcript:
            return jsonify({'error': 'Transcript is required'}), 400
        
        # Validate model
        allowed_models = [
            'meta-llama/llama-4-scout-17b-16e-instruct',
            'llama-3.3-70b-versatile'
        ]
        if model not in allowed_models:
            return jsonify({'error': 'Invalid model selected'}), 400
        
        # Get key points
        key_points = get_key_points(transcript, model)
        if key_points is None:
            return jsonify({'error': 'Could not generate key points. The AI service may be temporarily unavailable.'}), 500
        
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
    
    app.run(debug=True, host='0.0.0.0', port=3000)
    # app.run()