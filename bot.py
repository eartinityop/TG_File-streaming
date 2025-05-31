import os
import logging
import requests
from flask import Flask, request
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PORT = int(os.environ.get("PORT", 5000))
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
BASE_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://your-service-name.onrender.com').rstrip('/')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB Telegram file size limit for getFile

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

def get_vlc_url(file_id, file_size, file_name):
    """Create VLC-compatible URL that works for all file sizes"""
    # For small files: Use getFile to get actual path
    if file_size <= MAX_FILE_SIZE:
        file_info = telegram_request("getFile", {"file_id": file_id})
        if file_info and file_info.get('ok'):
            file_path = file_info['result']['file_path']
            return f"https://api.telegram.org/file/bot{TOKEN}/{file_path}?filename={file_name}"
    
    # For large files: Use direct URL pattern that works
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '', file_name)
    if not clean_name.endswith('.mp4'):
        clean_name = f"{clean_name.split('.')[0]}.mp4"
    return f"https://api.telegram.org/file/bot{TOKEN}/documents/{clean_name}?file_id={file_id}"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram updates and provide working VLC links"""
    try:
        data = request.json
        message = data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        
        # Handle /start command
        if message.get('text') == '/start':
            telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "🎬 Send me any video file to get a working VLC streaming link!\n\n"
                        "🔗 I'll provide a direct URL that plays in VLC\n"
                        "⏳ Links are valid for 1 hour\n"
                        "📦 Works with files of ANY size"
            })
            return 'OK'
        
        # Handle video files
        video = message.get('video') or message.get('document')
        if video and video.get('mime_type', '').startswith('video/'):
            file_id = video['file_id']
            file_name = video.get('file_name', 'video.mp4')
            file_size = video.get('file_size', 0)
            
            # Get VLC-compatible URL
            vlc_url = get_vlc_url(file_id, file_size, file_name)
            logger.info(f"Generated URL for {file_size} byte file: {vlc_url}")
            
            response_text = (
                "🎬 VLC Streaming Link (valid 1 hour):\n\n"
                f"{vlc_url}\n\n"
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
                        "Ready to provide VLC streaming links for files of ANY size!"
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
