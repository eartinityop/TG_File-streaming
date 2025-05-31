import os
import uuid
import logging
from flask import Flask, request, send_from_directory
from telegram import Update
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

# Create Telegram Application
application = Application.builder().token(TOKEN).build()

# Define handlers
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if message.video:
            file_obj = message.video
        elif message.document and message.document.mime_type.startswith('video/'):
            file_obj = message.document
        else:
            await message.reply_text("Please send a video file")
            return

        # Generate unique filename
        file_name = file_obj.file_name or "video"
        file_ext = os.path.splitext(file_name)[1] if '.' in file_name else '.mp4'
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        
        # Download file
        tg_file = await context.bot.get_file(file_obj.file_id)
        file_path = os.path.join(MEDIA_FOLDER, unique_filename)
        await tg_file.download_to_drive(custom_path=file_path)
        
        # Get base URL
        base_url = request.host_url.rstrip('/')
        stream_url = f"{base_url}/media/{unique_filename}"
        
        response = (
            "🎬 VLC Streaming Link:\n\n"
            f"`{stream_url}`\n\n"
            "1. Open VLC Player\n"
            "2. Media > Open Network Stream\n"
            "3. Paste above URL\n"
            "4. Click Play"
        )
        
        await message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text("❌ Error processing video")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📹 Send me any video file to get a VLC streaming link!")

# Register handlers
application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(
    filters.VIDEO | (filters.ATTACHMENT & filters.Document.MimeType("video/*")),
    handle_video
))

# Flask routes
@app.route('/media/<filename>')
def serve_media(filename):
    return send_from_directory(MEDIA_FOLDER, filename)

# CRITICAL FIX: Make sure this accepts POST requests
@app.route('/webhook', methods=['POST'])  # <-- ADD THIS
async def webhook():
    await application.update_queue.put(Update.de_json(request.json, application.bot))
    return 'OK', 200

# Health check
@app.route('/')
def health_check():
    return "Video Stream Bot is Running!", 200

# NEW: Webhook setup on startup
@app.before_first_request
def setup_webhook():
    webhook_url = f"https://{app.config.get('HOST', request.host)}/webhook"
    application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook configured to: {webhook_url}")

def main():
    app.run(host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    main()
