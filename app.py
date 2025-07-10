from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
import re
import os

app = Flask(__name__)

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