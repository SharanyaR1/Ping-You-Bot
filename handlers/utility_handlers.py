from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.connection import get_db

db = get_db()
subscription_collection = db["user_subscriptions"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 *Welcome to PingYou Bot!*\n\n"
        "🔔 *What I do:* Monitor groups and alert you when your keywords are mentioned.\n\n"
        "✨ *Main Commands:*\n"
        "/groups - View and manage your groups\n"
        "/use - Select a group to manage keywords\n"
        "/add - Add keywords to track\n"
        "/remove - Remove keywords\n"
        "/keywords - View all your tracked keywords\n\n"
        "🛠️ Type /help for full command list"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
    pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🛠️ *PingYou Bot Help*

*Group Management:*
/groups - View all groups and your status
/join - Subscribe to a group
/mute - Temporarily mute notifications
/leave - Permanently leave a group
/reset - Delete ALL your data (careful!)

*Keyword Management:*
/use - Select group to manage
/add - Add keywords (comma-separated)
/remove - Remove keywords
/list - Show keywords in current group
/keywords - View all keywords across groups
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")
    pass

MAX_MESSAGE_LENGTH = 390  # Leave buffer under Telegram’s 4096 limit
KEYWORDS_PER_PAGE = 1      # Number of groups per page

async def keywords_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    page = context.user_data.get("kw_page", 0)

    subscriptions = list(subscription_collection.find({
        "user_id": user_id,
        "subscribed": True
    }))

    if not subscriptions:
        if update.message:
            await update.message.reply_text("ℹ️ You don't have any active keyword subscriptions.")
        else:
            await update.callback_query.edit_message_text("ℹ️ You don't have any active keyword subscriptions.")
        return

    total_groups = len(subscriptions)
    total_keywords = sum(len(sub.get("keywords", [])) for sub in subscriptions)

    # Pagination logic
    start = page * KEYWORDS_PER_PAGE
    end = start + KEYWORDS_PER_PAGE
    current_groups = subscriptions[start:end]

    message = [f"🔍 *Your Keyword Dashboard*\n(Page {page + 1} of {(total_groups - 1) // KEYWORDS_PER_PAGE + 1})\n"]
    
    for sub in current_groups:
        group_name = sub.get("group_name", f"Group {sub['group_id']}")
        keywords = sub.get("keywords", [])

        if keywords:
            section = [f"*📌 {group_name}* ({len(keywords)} keywords)"]
            section += [f"• `{kw}`" for kw in keywords]
        else:
            section = [f"*📌 {group_name}*", "⚠️ No keywords tracked in this group yet."]
            
        section_text = "\n".join(section)
        
        if sum(len(line) + 1 for line in message) + len(section_text) > MAX_MESSAGE_LENGTH:
            break
        
        message.append(section_text)

    message.append(f"\n*ℹ️ Total: {total_groups} groups, {total_keywords} keywords*")

    buttons = []
    if start > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="kwpage_prev_page"))
    if end < total_groups:
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data="kwpage_next_page"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
    text = "\n".join(message)

    if update.message:  # Triggered by /keywords
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:  # Triggered by inline buttons
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def handle_keyword_page_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Prevents Telegram "loading..." effect

    direction = query.data
    page = context.user_data.get("kw_page", 0)

    if direction == "kwpage_next_page":
        context.user_data["kw_page"] = page + 1
    elif direction == "kwpage_prev_page" and page > 0:
        context.user_data["kw_page"] = page - 1

    await keywords_overview(update, context)  # No delete_message


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nuclear option to leave all groups and delete all data"""
    user_id = update.effective_user.id
    
    confirm_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ CONFIRM RESET ALL", callback_data="confirm_reset")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_reset")]
    ])
    
    await update.message.reply_text(
        "🚨 *Danger Zone* 🚨\n\n"
        "This will:\n"
        "1. Remove ALL your keywords\n"
        "2. Unsubscribe from ALL groups\n"
        "3. Delete ALL your data\n\n"
        "This cannot be undone!",
        reply_markup=confirm_keyboard,
        parse_mode="Markdown"
    )

async def handle_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "confirm_reset":
        subscription_collection.delete_many({"user_id": user_id})
        await query.edit_message_text(
            "🧹 All your data has been completely reset.",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "Reset cancelled. Your data is safe.",
            parse_mode="Markdown"
        )