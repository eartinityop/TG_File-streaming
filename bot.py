import os
import uuid
import logging
import requests
from flask import Flask, request, send_from_directory

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MEDIA_FOLDER = "media"
PORT = int(os.environ.get("PORT", 5000))
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
BASE_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://your-service-name.onrender.com').rstrip('/')
MAX_DOWNLOAD_SIZE = 20 * 1024 * 1024  # 20MB (Render free tier limit)

# Ensure media folder exists
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Create Flask app
app = Flask(__name__)

def telegram_request(method, data=None):
    """Make synchronous request to Telegram API"""
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Telegram API error: {e}")
        return None

def download_file(file_id, file_path):
    """Download file from Telegram if under size limit"""
    try:
        # Get file info
        file_info = telegram_request("getFile", {"file_id": file_id})
        if not file_info or not file_info.get('ok'):
            return False, "Failed to get file info"
            
        file_size = file_info['result'].get('file_size', 0)
        if file_size > MAX_DOWNLOAD_SIZE:
            return False, f"File too large ({file_size//(1024*1024)}MB)"
            
        # Download file
        file_path_tg = file_info['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path_tg}"
        
        response = requests.get(file_url, stream=True, timeout=30)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return True, "Downloaded"
        return False, "Download failed"
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False, str(e)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram updates"""
    try:
        data = request.json
        message = data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        
        # Handle /start command
        if message.get('text') == '/start':
            telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "🎬 Send me any video file to get a VLC streaming link!\n\n"
                        "📦 For small files (<20MB): Permanent streaming link\n"
                        "⏳ For large files: Direct link (valid 1 hour)"
            })
            return 'OK'
        
        # Handle video files
        video = message.get('video') or message.get('document')
        if video and video.get('mime_type', '').startswith('video/'):
            file_id = video['file_id']
            file_name = video.get('file_name', 'video.mp4')
            file_size = video.get('file_size', 0)
            
            # Get file info from Telegram
            file_info = telegram_request("getFile", {"file_id": file_id})
            if not file_info or not file_info.get('ok'):
                logger.error(f"File info error: {file_info}")
                telegram_request("sendMessage", {
                    "chat_id": chat_id,
                    "text": "❌ Failed to get file info from Telegram"
                })
                return 'OK'
            
            file_path_tg = file_info['result']['file_path']
            telegram_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path_tg}"
            
            # Handle small files (download to server)
            if file_size <= MAX_DOWNLOAD_SIZE:
                file_ext = os.path.splitext(file_name)[1] or '.mp4'
                unique_filename = f"{uuid.uuid4()}{file_ext}"
                file_path = os.path.join(MEDIA_FOLDER, unique_filename)
                
                # Try to download
                success, reason = download_file(file_id, file_path)
                if success:
                    stream_url = f"{BASE_URL}/media/{unique_filename}"
                    response_text = (
                        "🎬 VLC Streaming Link (Permanent):\n\n"
                        f"{stream_url}\n\n"
                        "1. Open VLC Player\n"
                        "2. Media > Open Network Stream\n"
                        "3. Paste above URL\n"
                        "4. Click Play"
                    )
                else:
                    response_text = (
                        "❌ Couldn't save video locally\n\n"
                        "🔗 Direct Telegram Link (valid 1 hour):\n"
                        f"{telegram_url}"
                    )
            else:
                # For large files - use direct Telegram URL
                response_text = (
                    "🔗 Direct Streaming Link (valid 1 hour):\n\n"
                    f"{telegram_url}\n\n"
                    "1. Open VLC Player\n"
                    "2. Media > Open Network Stream\n"
                    "3. Paste above URL\n"
                    "4. Click Play\n\n"
                    "⚠️ Note: Link expires in 1 hour"
                )
            
            telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": response_text
            })
        
        return 'OK'
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'ERROR', 500

@app.route('/media/<filename>')
def serve_media(filename):
    """Serve downloaded video files"""
    return send_from_directory(MEDIA_FOLDER, filename)

@app.route('/')
def health_check():
    return "Video Stream Bot is Running!", 200

def setup_webhook():
    """Configure Telegram webhook"""
    try:
        webhook_url = f"{BASE_URL}/webhook"
        response = telegram_request("setWebhook", {"url": webhook_url})
        
        if response and response.get('ok'):
            logger.info(f"Webhook set to: {webhook_url}")
            # Send admin notification
            telegram_request("sendMessage", {
                "chat_id": ADMIN_CHAT_ID,
                "text": f"🤖 Bot started successfully!\nWebhook: {webhook_url}\n"
                        f"Max download size: {MAX_DOWNLOAD_SIZE//(1024*1024)}MB"
            })
            return True
        else:
            error = response.get('description') if response else "Unknown error"
            logger.error(f"Webhook setup failed: {error}")
            return False
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
        return False

# Initialize on startup
if __name__ == "__main__":
    # Set webhook
    setup_webhook()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=PORT, debug=False)
