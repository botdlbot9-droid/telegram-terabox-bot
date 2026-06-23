import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from terabox_api import TeraBoxClient
import os


TERABOX_EMAIL = os.getenv("TERABOX_EMAIL")
TERABOX_PASS = os.getenv("https://terabox-player.rishuapi.workers.dev/?url=https://terabox.com/s/1kpYz6J8xalpQtoDk4DH8Aw")
BOT_TOKEN = os.getenv("8669431607:AAHz2inj95ZmsmD4w1MmGH7ybhaY5jvp8EQ")

client = TeraBoxClient(TERABOX_EMAIL, "https://terabox-player.rishuapi.workers.dev/?url=https://terabox.com/s/1kpYz6J8xalpQtoDk4DH8Aw")

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to TeraBox Bot!")

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = client.list_files()
    reply = "\n".join([f"{f['name']} (ID: {f['id']})" for f in files])
    await update.message.reply_text(reply or "📂 No files found.")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_files))

app.run_polling()
