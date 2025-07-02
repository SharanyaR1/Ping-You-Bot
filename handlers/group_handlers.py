from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.connection import get_db

db = get_db()
group_collection = db["bot_groups"]
subscription_collection = db["user_subscriptions"]

async def bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = update.my_chat_member
    if member.new_chat_member.status == "member":
        chat = member.chat
        group_id = chat.id
        group_name = chat.title

        existing = group_collection.find_one({"group_id": group_id})
        if not existing:
            group_collection.insert_one({"group_id": group_id, "group_name": group_name})

GROUPS_PER_PAGE = 5  # You can tweak this limit as needed

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    user_id = update.effective_user.id
    all_groups = list(group_collection.find({}))
    user_subs = list(subscription_collection.find({"user_id": user_id}))
    sub_map = {sub["group_id"]: sub for sub in user_subs}

    if not all_groups:
        await update.message.reply_text(
            "😕 No active groups found.\n\nYou need to be in at least one group *with the bot added*.",
            parse_mode="Markdown"
        )
        return

    total_pages = (len(all_groups) - 1) // GROUPS_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))  # Clamp page number

    start = page * GROUPS_PER_PAGE
    end = start + GROUPS_PER_PAGE
    paginated_groups = all_groups[start:end]

    # 📋 Header and Legend
    message = (
        "📋 *Your Groups*\n\n"
        "These are the groups you and the bot are part of.\n\n"
        "🟢 Tracking – You’ll receive notifications for matching keywords\n"
        "🔴 Muted – Notifications are turned off for this group\n"
        "⚪️ Not Tracking – You haven’t enabled keyword alerts for this group\n\n"
    )

    buttons = []

    for group in paginated_groups:
        group_id = group["group_id"]
        status = "⚪️ Not Tracking"
        if group_id in sub_map:
            subscribed = sub_map[group_id].get("subscribed", False)
            status = "🟢 Tracking" if subscribed else "🔴 Muted"


        buttons.append([
            InlineKeyboardButton(
                f"{group['group_name']} - {status}",
                callback_data=f"group_{group['group_id']}"
            )
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"group_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ View more groups", callback_data=f"group_page_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                print(f"Error editing message: {e}")
    else:
        await update.message.reply_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def group_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed group options"""
    query = update.callback_query
    await query.answer()
    
    group_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    # Get group info
    group = group_collection.find_one({"group_id": group_id})
    sub = subscription_collection.find_one({"user_id": user_id, "group_id": group_id})

    # Determine status label
    if sub:
        subscribed = sub.get("subscribed", False)
        status = "🟢 Tracking" if subscribed else "🔴 Muted"
    else:
        subscribed = None
        status = "⚪️ Not Tracking"
    
    buttons = []

        # Build action buttons
    buttons = []

    if subscribed is True:
        buttons.append([InlineKeyboardButton("🔇 Mute Notifications", callback_data=f"mute_{group_id}")])
    elif subscribed is False:
        buttons.append([InlineKeyboardButton("🔔 Enable Notifications", callback_data=f"join_{group_id}")])
    else:  # not subscribed at all
        buttons.append([InlineKeyboardButton("➕ Start Tracking", callback_data=f"join_{group_id}")])

    if sub:
        buttons.append([InlineKeyboardButton("🚪 Leave Group", callback_data=f"leave_{group_id}")])

    buttons.append([InlineKeyboardButton("🔙 Back to List", callback_data="back_to_groups")])
 
    
    await query.edit_message_text(
        f"⚙️ *{group['group_name']}*\nStatus: {status}",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    pass

async def handle_group_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data == "back_to_groups":
        await list_groups(update, context)
        return

    if data.startswith("group_page_"):
        page = int(data.split("_")[2])
        await list_groups(update, context, page)
        return

    if data.startswith("group_"):
        await group_detail(update, context)
        return

    if data.startswith("join_"):
        group_id = int(data.split("_")[1])
        group = group_collection.find_one({"group_id": group_id})
        sub = subscription_collection.find_one({"user_id": user_id, "group_id": group_id})
        keywords = sub.get("keywords", []) if sub else []

        subscription_collection.update_one(
            {"user_id": user_id, "group_id": group_id},
            {
                "$set": {
                    "subscribed": True,
                    "group_name": group["group_name"],
                    "keywords": keywords
                }
            },
            upsert=True
        )
        await query.answer("🔔 Notifications enabled!")
        await group_detail(update, context)

    elif data.startswith("mute_"):
        group_id = int(data.split("_")[1])
        subscription_collection.update_one(
            {"user_id": user_id, "group_id": group_id},
            {"$set": {"subscribed": False}}
        )
        await query.answer("🔇 Notifications muted")
        await group_detail(update, context)

    elif data.startswith("leave_"):
        group_id = int(data.split("_")[1])
        subscription_collection.delete_one(
            {"user_id": user_id, "group_id": group_id}
        )
        await query.answer("🚪 Left group")
        await list_groups(update, context)
