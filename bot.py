import logging
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from terabox_api import TeraBoxClient

# ============= CONFIGURATION =============
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("Missing BOT_TOKEN! Please set it in environment variables.")
    exit(1)

# Initialize TeraBox Client (no credentials needed - ndus is embedded)
try:
    terabox = TeraBoxClient()
    logger.info("✅ TeraBox client initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize TeraBox client: {e}")
    exit(1)

# ============= BOT HANDLERS =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🚀 **Welcome to TeraBox Bot!**

I can help you manage your TeraBox files directly from Telegram.

**Available Commands:**
/start - Show this message
/list - List files in your TeraBox
/upload - Upload a file (reply to a file with /upload)
/download - Download a file (use /download <file_id>)
/mkdir - Create a new folder (use /mkdir <folder_name>)
/delete - Delete a file (use /delete <file_id>)
/help - Show detailed help

**How to use:**
• Send any file to upload it to TeraBox
• Use /list to see your files
• Use /download <file_id> to download a file
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 **Detailed Help**

**Upload Files:**
Just send any file (photo, video, document) and it will be automatically uploaded to TeraBox.

**List Files:**
Use /list to see all files in your root directory.

**Download Files:**
Use /download <file_id> - You can get file_id from /list command.

**Create Folder:**
Use /mkdir <folder_name> to create a new folder.

**Delete File:**
Use /delete <file_id> to delete a file.

**File IDs:**
When you use /list, you'll see each file with its ID in parentheses.
Example: `myfile.jpg (ID: 123456789)`
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("📂 Fetching your files...")
        files = terabox.list_files(limit=50)
        if not files:
            await update.message.reply_text("📭 No files found in your TeraBox.")
            return
        
        reply = "📁 **Your Files:**\n\n"
        for item in files:
            icon = "📁" if item.get("isdir") == 1 else "📄"
            name = item.get("name", "Unknown")
            file_id = item.get("fs_id", "N/A")
            size = item.get("size", 0)
            
            if size > 1024 * 1024 * 1024:
                size_str = f"{size / (1024*1024*1024):.2f} GB"
            elif size > 1024 * 1024:
                size_str = f"{size / (1024*1024):.2f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.2f} KB"
            else:
                size_str = f"{size} B"
            
            reply += f"{icon} `{name}`\n"
            reply += f"   📎 ID: `{file_id}` | 📦 Size: {size_str}\n\n"
        
        if len(reply) > 4000:
            parts = [reply[i:i+4000] for i in range(0, len(reply), 4000)]
            for part in parts:
                await update.message.reply_text(part, parse_mode="Markdown")
        else:
            await update.message.reply_text(reply, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"List error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def download_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a file ID.\n"
                "Usage: `/download <file_id>`\n"
                "Get file IDs from /list command.",
                parse_mode="Markdown"
            )
            return
        
        file_id = context.args[0]
        await update.message.reply_text(f"⬇️ Downloading file (ID: {file_id})...")
        
        file_content = terabox.download_file(file_id)
        
        files = terabox.list_files(limit=100)
        filename = "downloaded_file"
        for f in files:
            if str(f.get("fs_id")) == str(file_id):
                filename = f.get("name", "downloaded_file")
                break
        
        await update.message.reply_document(
            document=file_content,
            filename=filename,
            caption=f"✅ Downloaded from TeraBox\nFile ID: {file_id}"
        )
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.message.reply_text(f"❌ Download failed: {str(e)}")

async def upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not (update.message.document or update.message.photo or update.message.video):
            await update.message.reply_text(
                "❌ Please send a file (document, photo, or video) to upload."
            )
            return
        
        if update.message.document:
            file_obj = update.message.document
            file_name = file_obj.file_name or "document"
        elif update.message.photo:
            file_obj = update.message.photo[-1]
            file_name = f"photo_{file_obj.file_id}.jpg"
        elif update.message.video:
            file_obj = update.message.video
            file_name = file_obj.file_name or f"video_{file_obj.file_id}.mp4"
        else:
            return
        
        await update.message.reply_text(f"⬆️ Uploading `{file_name}` to TeraBox...", parse_mode="Markdown")
        
        file = await file_obj.get_file()
        temp_path = f"/tmp/{file_name}"
        await file.download_to_drive(temp_path)
        
        result = terabox.upload_file(temp_path, "/")
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        if result.get("success"):
            await update.message.reply_text(
                f"✅ **Upload Successful!**\n\n"
                f"📄 File: `{file_name}`\n"
                f"📁 Location: Root directory\n"
                f"🔄 Status: {result.get('message', 'Completed')}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ Upload failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await update.message.reply_text(f"❌ Upload failed: {str(e)}")

async def create_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a folder name.\n"
                "Usage: `/mkdir <folder_name>`",
                parse_mode="Markdown"
            )
            return
        
        folder_name = " ".join(context.args)
        await update.message.reply_text(f"📁 Creating folder `{folder_name}`...", parse_mode="Markdown")
        
        terabox.create_folder(folder_name, "/")
        await update.message.reply_text(f"✅ Folder `{folder_name}` created successfully!", parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Create folder error: {e}")
        await update.message.reply_text(f"❌ Failed to create folder: {str(e)}")

async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a file ID.\n"
                "Usage: `/delete <file_id>`\n"
                "Get file IDs from /list command.",
                parse_mode="Markdown"
            )
            return
        
        file_id = context.args[0]
        await update.message.reply_text(f"🗑️ Deleting file (ID: {file_id})...")
        
        terabox.delete_file(file_id)
        await update.message.reply_text(f"✅ File deleted successfully!")
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        await update.message.reply_text(f"❌ Delete failed: {str(e)}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Unknown command. Use /start to see available commands."
    )

# ============= MAIN =============

def main():
    logger.info("🚀 Starting TeraBox Bot...")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("download", download_file))
    app.add_handler(CommandHandler("mkdir", create_folder))
    app.add_handler(CommandHandler("delete", delete_file))
    
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO,
        upload_handler
    ))
    
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    logger.info("✅ Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
