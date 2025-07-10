# YouTube Subtitle Extractor

A full-stack Flask application that extracts subtitles from YouTube videos based on URL input.

## Features

- 🎬 Extract subtitles from any YouTube video with available transcripts
- 🌐 Clean, modern web interface
- 📋 Copy transcript to clipboard
- 🔄 Real-time loading indicators
- 📱 Responsive design
- 🚀 RESTful API endpoint

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install Flask youtube-transcript-api
```

### 2. Project Structure

Create the following directory structure:
```
youtube-subtitle-extractor/
├── app.py
├── requirements.txt
├── templates/
│   └── index.html
└── static/ (optional, for additional CSS/JS files)
```

### 3. Run the Application

```bash
python app.py
```

The application will be available at: `http://localhost:5000`

## Usage

### Web Interface
1. Open your browser and go to `http://localhost:5000`
2. Enter a YouTube URL in the input field
3. Click "Extract Subtitles"
4. View and copy the extracted transcript

### API Endpoint

**POST** `/api/transcript`

Request body:
```json
{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
```

Response:
```json
{
    "video_id": "VIDEO_ID",
    "transcript": "Full transcript text...",
    "success": true
}
```

Error response:
```json
{
    "error": "Error message",
    "success": false
}
```

## Supported URL Formats

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/embed/VIDEO_ID`

## Error Handling

The application handles various error scenarios:
- Invalid YouTube URLs
- Videos without available transcripts
- Private or restricted videos
- Network errors
- Malformed requests

## Notes

- Only works with videos that have available transcripts/subtitles
- Supports auto-generated and manual subtitles
- The transcript is returned as plain text without timestamps
- Some videos may not have subtitles available in your preferred language