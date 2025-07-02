from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, filters
from database.connection import get_db

db = get_db()
subscription_collection = db["user_subscriptions"]

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    message_text = update.message.text.lower()
    group_id = update.effective_chat.id

    cursor = subscription_collection.find({"group_id": group_id, "subscribed": True})

    for doc in cursor:
        user_id = doc["user_id"]
        keywords = doc.get("keywords", [])

        matched_keywords = [kw for kw in keywords if kw.lower() in message_text]
        if matched_keywords:
            try:
                highlighted = message_text
                for kw in matched_keywords:
                    highlighted = highlighted.replace(kw, f"*{kw}*")

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                msg_id = update.message.message_id

                if update.effective_chat.username:
                    message_link = f"https://t.me/{update.effective_chat.username}/{msg_id}"
                    link_text = f"[View message]({message_link})"
                else:
                    link_text = "_Message link unavailable (private group)_"

                sender = update.effective_user
                sender_name = sender.full_name
                sender_username = f"(@{sender.username})" if sender.username else ""

                group_name = doc.get('group_name', 'Unknown Group')

                msg = (
                    f"📌 *Keyword Match!*\n"
                    f"🔍 *Matched:* {', '.join(f'`{kw}`' for kw in matched_keywords)}\n"
                    f"👤 *Sender:* {sender_name} {sender_username}\n"
                    f"👥 *Group:* `{group_name}`\n"
                    f"🕒 *Time:* `{timestamp}`\n"
                    f"{link_text}\n\n"
                    f"🗨️ *Message:* {highlighted}"
                )

                await context.bot.send_message(
                    chat_id=user_id,
                    text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )

                subscription_collection.update_one(
                    {"user_id": user_id, "group_id": group_id},
                    {"$set": {"last_match_time": timestamp}}
                )

            except Exception as e:
                print(f"Failed to forward to user {user_id}: {e}")

    pass