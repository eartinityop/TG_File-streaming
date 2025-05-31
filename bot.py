import os
import logging
import requests
from flask import Flask, request
import mimetypes

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

def get_vlc_url(file_id, mime_type):
    """Create VLC-compatible URL with proper extension"""
    # Determine file extension from MIME type
    ext = mimetypes.guess_extension(mime_type) or ".mp4"
    
    # Create VLC-friendly URL with extension
    return f"https://api.telegram.org/file/bot{TOKEN}/{file_id}{ext}"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram updates and provide VLC-compatible links"""
    try:
        data = request.json
        message = data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        
        # Handle /start command
        if message.get('text') == '/start':
            telegram_request("sendMessage", {
                "chat_id": chat_id,
                "text": "🎬 Send me any video file to get a VLC streaming link!\n\n"
                        "🔗 I'll provide a URL that works directly in VLC\n"
                        "⏳ Links are valid for 1 hour"
            })
            return 'OK'
        
        # Handle video files
        video = message.get('video') or message.get('document')
        if video and video.get('mime_type', '').startswith('video/'):
            file_id = video['file_id']
            mime_type = video['mime_type']
            
            # Get VLC-compatible URL
            vlc_url = get_vlc_url(file_id, mime_type)
            
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
                        "Ready to provide VLC-compatible links!"
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
