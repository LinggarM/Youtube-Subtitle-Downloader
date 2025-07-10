# YouTube Subtitle Extractor

A full-stack Flask application that extracts subtitles from YouTube videos based on URL input.

## Features

- 🎬 Extract subtitles from any YouTube video with available transcripts
- 🌐 **Language Selection**: Choose from available subtitle languages
- 🔍 **Language Detection**: Automatically detect all available subtitle languages
- 🏷️ **Language Info**: Shows auto-generated vs manual subtitles
- 🌐 Clean, modern web interface
- 📋 Copy transcript to clipboard
- 🔄 Real-time loading indicators
- 📱 Responsive design
- 🚀 RESTful API endpoints

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
3. Click "Check Languages" to see available subtitle languages
4. Select your preferred language from the list
5. Click "Extract Subtitles" to get the transcript
6. View and copy the extracted transcript

### API Endpoints

**POST** `/api/languages`
Get available subtitle languages for a video.

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
    "languages": [
        {
            "language_code": "en",
            "language": "English",
            "is_generated": true,
            "is_translatable": true
        },
        {
            "language_code": "es",
            "language": "Spanish",
            "is_generated": false,
            "is_translatable": false
        }
    ],
    "success": true
}
```

**POST** `/api/transcript`
Extract transcript in specified language.

Request body:
```json
{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "language_code": "en"
}
```

Response:
```json
{
    "video_id": "VIDEO_ID",
    "transcript": "Full transcript text...",
    "language_code": "en",
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

## Language Selection

The application now supports multiple subtitle languages:

- **Auto-detection**: Automatically detects all available subtitle languages
- **Manual vs Auto-generated**: Shows whether subtitles are manually created or auto-generated
- **Translatable**: Indicates if subtitles can be translated to other languages
- **Language codes**: Displays standard language codes (en, es, fr, etc.)
- **Fallback**: Falls back to default language if selected language is unavailable

## Error Handling

The application handles various error scenarios:
- Invalid YouTube URLs
- Videos without available transcripts
- Selected language not available
- Private or restricted videos
- Network errors
- Malformed requests

## Notes

- Only works with videos that have available transcripts/subtitles
- Supports both manual and auto-generated subtitles
- Language selection shows additional metadata (auto-generated, translatable)
- The transcript is returned as plain text without timestamps
- If a specific language is not available, the system will attempt to use the default language