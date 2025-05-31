import os
import uuid
import logging
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
MEDIA_FOLDER = "media"

# Ensure media folder exists
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Create Flask app for serving files
app = Flask(__name__)

@app.route('/media/<filename>')
def serve_media(filename):
    """Serve video files through Flask"""
    return send_from_directory(MEDIA_FOLDER, filename)

async def download_video(file_obj, context, filename):
    """Download video file to server"""
    file_path = os.path.join(MEDIA_FOLDER, filename)
    
    # Download the file
    await file_obj.download_to_drive(custom_path=file_path)
    
    logger.info(f"Video saved: {filename}")
    return f"{RENDER_EXTERNAL_URL}/media/{filename}"

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video files and generate persistent links"""
    try:
        message = update.message
        
        # Determine file type
        if message.video:
            file_obj = message.video
        elif message.document and message.document.mime_type.startswith('video/'):
            file_obj = message.document
        else:
            await message.reply_text("Please send a video file (MP4, MKV, MOV, etc.)")
            return

        # Generate unique filename
        file_ext = os.path.splitext(file_obj.file_name)[1] if file_obj.file_name else ".mp4"
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        
        # Get file object
        tg_file = await context.bot.get_file(file_obj.file_id)
        
        # Download file to server
        stream_url = await download_video(tg_file, context, unique_filename)
        
        # Create response message
        response = (
            "🎬 VLC Streaming Link (Persistent):\n\n"
            f"`{stream_url}`\n\n"
            "**How to use:**\n"
            "1. Open VLC Player\n"
            "2. Go to Media > Open Network Stream\n"
            "3. Paste this URL\n"
            "4. Click Play\n\n"
            "⚠️ Note: Link remains valid as long as server is running"
        )
        
        await message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await message.reply_text("❌ Error processing video. Please try again.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text(
        "📹 Send me any video file to get a persistent VLC streaming link!\n\n"
        "I'll store it on the server and generate a URL that works in VLC's Network Stream option."
    )

def run_bot():
    """Start the Telegram bot"""
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(
        filters.VIDEO | (filters.DOCUMENT & filters.Document.MimeType("video/*")),
        handle_video
    ))
    
    # Set up webhook for Render
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=f"{RENDER_EXTERNAL_URL}/telegram",
        secret_token=WEBHOOK_SECRET
    )

if __name__ == "__main__":
    # Start Flask app in separate thread
    from threading import Thread
    Thread(target=app.run, kwargs={
        'host': '0.0.0.0',
        'port': int(os.environ.get("PORT", 5000))
    }).start()
    
    # Start Telegram bot
    run_bot()
