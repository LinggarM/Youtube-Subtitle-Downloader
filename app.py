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

def get_transcript_text(video_id):
    """Get transcript text from video ID"""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        subtitle = ''
        for index, value in enumerate(transcript):
            if index == 0:
                subtitle = subtitle + (value['text'])
            else:
                subtitle = subtitle + ' ' + (value['text'])
        return subtitle
    except Exception as e:
        return None

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/transcript', methods=['POST'])
def get_transcript():
    """API endpoint to get transcript from YouTube URL"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Extract video ID from URL
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        # Get transcript
        transcript = get_transcript_text(video_id)
        if transcript is None:
            return jsonify({'error': 'Could not retrieve transcript. Video may not have subtitles or may be private.'}), 404
        
        return jsonify({
            'video_id': video_id,
            'transcript': transcript,
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
    # app.run(debug=True, host='127.0.0.1', port=5000)
    app.run()