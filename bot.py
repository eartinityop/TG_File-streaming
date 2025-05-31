import os
import uuid
import logging
from flask import Flask, request, send_from_directory
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

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

# Ensure media folder exists
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Create Flask app
app = Flask(__name__)

# Create bot instance
bot = Bot(token=TOKEN)

# Initialize application
application = Application.builder().token(TOKEN).build()

# Define handlers
def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        
        # Determine file type
        if message.video:
            file_obj = message.video
        elif message.document and message.document.mime_type.startswith('video/'):
            file_obj = message.document
        else:
            context.bot.send_message(chat_id=message.chat_id, text="Please send a video file")
            return

        # Generate unique filename
        file_name = file_obj.file_name or "video"
        file_ext = os.path.splitext(file_name)[1] if '.' in file_name else '.mp4'
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        
        # Download file to server
        tg_file = bot.get_file(file_obj.file_id)
        file_path = os.path.join(MEDIA_FOLDER, unique_filename)
        tg_file.download(custom_path=file_path)
        
        # Get base URL
        base_url = os.getenv('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
        stream_url = f"{base_url}/media/{unique_filename}"
        
        # Create response
        response = (
            "🎬 VLC Streaming Link:\n\n"
            f"{stream_url}\n\n"
            "1. Open VLC Player\n"
            "2. Media > Open Network Stream\n"
            "3. Paste above URL\n"
            "4. Click Play"
        )
        
        context.bot.send_message(chat_id=message.chat_id, text=response)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        context.bot.send_message(chat_id=message.chat_id, text="❌ Error processing video")

def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text="📹 Send me any video file to get a VLC streaming link!"
    )

# Register handlers
application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(
    filters.VIDEO | (filters.ATTACHMENT & filters.Document.MimeType("video/*")),
    handle_video
))

# Flask route for serving media files
@app.route('/media/<filename>')
def serve_media(filename):
    return send_from_directory(MEDIA_FOLDER, filename)

# Flask route for Telegram webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.json, bot)
    application.process_update(update)
    return 'OK', 200

@app.route('/')
def health_check():
    return "Video Stream Bot is Running!", 200

# Set webhook on startup
def setup_webhook():
    try:
        # Get Render URL
        render_url = os.getenv('RENDER_EXTERNAL_URL', '').rstrip('/')
        if not render_url:
            # Use request context if available
            render_url = request.host_url.rstrip('/') if request else "https://your-service.onrender.com"
        
        webhook_url = f"{render_url}/webhook"
        
        # Set webhook
        bot.set_webhook(webhook_url)
        logger.info(f"Webhook configured to: {webhook_url}")
        
        # Test message
        bot.send_message(
            chat_id=os.getenv('ADMIN_CHAT_ID'),
            text=f"🤖 Bot started successfully!\nWebhook: {webhook_url}"
        )
        return True
    except Exception as e:
        logger.error(f"Webhook setup failed: {e}")
        return False

# Run webhook setup when app starts
setup_webhook()

def main():
    app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == "__main__":
    main()
