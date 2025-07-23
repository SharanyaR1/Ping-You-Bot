from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.connection import get_db

db = get_db()
subscription_collection = db["user_subscriptions"]
group_collection = db["bot_groups"]

async def use_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_subs = list(subscription_collection.find({"user_id": user_id, "subscribed": True}))

    if not user_subs:
        await update.message.reply_text("❗️ You are not subscribed to any group yet.")
        return

    buttons = [
        [InlineKeyboardButton(sub["group_name"], callback_data=f"use|{sub['group_id']}")]
        for sub in user_subs
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a group to manage keywords:", reply_markup=keyboard)

async def handle_use_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("|")
    
    if len(parts) == 3:  # New format with group_name
        action, group_id, group_name = parts
    elif len(parts) == 2:  # Old format for backward compatibility
        action, group_id = parts
        # Fetch group name from database if not provided
        group = group_collection.find_one({"group_id": int(group_id)})
        group_name = group.get("group_name", f"Group {group_id}") if group else f"Group {group_id}"
    else:
        await query.edit_message_text("❗️ Invalid data format")
        return

    group_id = int(group_id)
    context.chat_data["active_group"] = group_id
    context.chat_data["active_group_name"] = group_name  # Store name for future reference
    
    await query.edit_message_text(f"✅ Managing keywords for: {group_name}", parse_mode="Markdown")

MAX_KEYWORDS_PER_ADD = 20
MAX_KEYWORDS_PER_GROUP = 50

async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if "active_group" not in context.chat_data:
        await update.message.reply_text("❗️ Use /use to select a group first.")
        return

    group_id = context.chat_data["active_group"]
    sub = subscription_collection.find_one({"user_id": user_id, "group_id": group_id})

    if not sub or not sub.get("subscribed", False):
        await update.message.reply_text("❗️ You are not subscribed to this group.")
        return

    if not context.args:
        await update.message.reply_text(
            "✏️ Please enter keywords after the command. Example:\n`/add python, ai, remote`",
            parse_mode="Markdown"
        )
        return

    # Parse and normalize
    input_text = " ".join(context.args)
    input_keywords = [kw.strip().lower() for kw in input_text.split(",") if kw.strip()]
    input_keywords = list(set(input_keywords))  # deduplicate input

    if len(input_keywords) > MAX_KEYWORDS_PER_ADD:
        await update.message.reply_text(f"🚫 You can add a maximum of {MAX_KEYWORDS_PER_ADD} keywords at once.")
        return

    existing_keywords = sub.get("keywords", [])
    remaining_slots = MAX_KEYWORDS_PER_GROUP - len(existing_keywords)

    # Filter out duplicates
    added_keywords = [kw for kw in input_keywords if kw not in existing_keywords][:remaining_slots]
    duplicate_keywords = [kw for kw in input_keywords if kw in existing_keywords]

    if not added_keywords:
        await update.message.reply_text("⚠️ No new keywords were added (already exist or limit reached).")
        return

    # Save
    subscription_collection.update_one(
        {"user_id": user_id, "group_id": group_id},
        {"$push": {"keywords": {"$each": added_keywords}}}
    )

    # Build response
    response = []

    # Add group name info at the top
    group = group_collection.find_one({"group_id": group_id})
    group_name = group.get("group_name", f"Group {group_id}") if group else f"Group {group_id}"
    response.append(f"📌 *Group:* {group_name}")

    if added_keywords:
        if len(added_keywords) == 1:
            response.append(f"✅ Added keyword: `{added_keywords[0]}`")
        else:
            bullet_list = "\n".join(f"• {kw}" for kw in added_keywords)
            response.append(f"✅ Added {len(added_keywords)} keywords:\n{bullet_list}")
    if duplicate_keywords:
        response.append(f"\n⚠️ Already exists: {', '.join(f'`{kw}`' for kw in duplicate_keywords)}")

    await update.message.reply_text("\n".join(response), parse_mode="Markdown")


async def list_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if "active_group" not in context.chat_data:
        await update.message.reply_text("❗️ Use /use to select a group first.")
        return

    group_id = context.chat_data["active_group"]
    sub = subscription_collection.find_one({"user_id": user_id, "group_id": group_id})

    if not sub or not sub.get("subscribed", False):
        await update.message.reply_text("❗️ You are not subscribed to this group.")
        return

    keywords = sub.get("keywords", [])
    if not keywords:
        await update.message.reply_text("No keywords found.")
    else:
        await update.message.reply_text("\n".join(f"• {kw}" for kw in keywords))

KEYWORDS_PER_PAGE = 10  # You can tweak this value

async def remove_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if "active_group" not in context.chat_data:
        await update.message.reply_text("❗️ Use /use to select a group first.")
        return

    group_id = context.chat_data["active_group"]
    sub = subscription_collection.find_one({"user_id": user_id, "group_id": group_id})

    if not sub or not sub.get("subscribed", False):
        await update.message.reply_text("❗️ You are not subscribed to this group.")
        return

    keywords = sub.get("keywords", [])
    if not keywords:
        await update.message.reply_text("⚡ You are not tracking any keywords yet.")
        return

    context.user_data["remove_kw_data"] = {
        "selected": set(),
        "all_keywords": keywords,
        "group_id": group_id,
        "page": 0
    }

    await show_remove_menu(update, context)


async def show_remove_menu(update, context):
    data = context.user_data.get("remove_kw_data", {})
    selected = data.get("selected", set())
    all_keywords = data.get("all_keywords", [])
    group_id = data.get("group_id")
    page = data.get("page", 0)

    group = group_collection.find_one({"group_id": group_id})
    group_name = group.get("group_name", f"Group {group_id}") if group else f"Group {group_id}"

    start = page * KEYWORDS_PER_PAGE
    end = start + KEYWORDS_PER_PAGE
    paginated_keywords = all_keywords[start:end]

    keyboard = []
    for kw in paginated_keywords:
        emoji = "✅" if kw in selected else "🔹"
        keyboard.append([InlineKeyboardButton(f"{emoji} {kw}", callback_data=f"kw_toggle:{kw}")])

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data="kw_prev_page"))
    if end < len(all_keywords):
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data="kw_next_page"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    action_buttons = []
    if selected:
        action_buttons.append(InlineKeyboardButton("🗑️ Remove Selected", callback_data="kw_remove_selected"))
    action_buttons.append(InlineKeyboardButton("💣 Remove ALL", callback_data="kw_remove_all"))
    keyboard.append(action_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        f"✏️ *Keyword Management for {group_name}*\n\n"
        f"📄 *Page {page + 1} of {(len(all_keywords) - 1) // KEYWORDS_PER_PAGE + 1}*\n"
        f"🔹 *{len(all_keywords)} tracked keywords*\n"
        f"✅ *{len(selected)} selected*\n\n"
        "Click keywords to select/deselect them"
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error updating message: {e}")
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )


async def handle_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if "remove_kw_data" not in context.user_data:
        await query.edit_message_text("⌛ Session expired. Please start over with /remove")
        return

    session = context.user_data["remove_kw_data"]
    user_id = query.from_user.id
    data = query.data

    if data.startswith("kw_toggle:"):
        keyword = data.split(":")[1]
        if keyword in session["selected"]:
            session["selected"].remove(keyword)
        else:
            session["selected"].add(keyword)
        await show_remove_menu(update, context)

    elif data == "kw_prev_page":
        session["page"] = max(0, session["page"] - 1)
        await show_remove_menu(update, context)

    elif data == "kw_next_page":
        total_pages = (len(session["all_keywords"]) - 1) // KEYWORDS_PER_PAGE
        session["page"] = min(total_pages, session["page"] + 1)
        await show_remove_menu(update, context)

    elif data == "kw_remove_selected":
        if not session["selected"]:
            await query.answer("❗ No keywords selected", show_alert=True)
            return

        subscription_collection.update_one(
            {"user_id": user_id, "group_id": session["group_id"]},
            {"$pull": {"keywords": {"$in": list(session["selected"])}}}
        )

        removed_count = len(session["selected"])
        await query.edit_message_text(
            f"🧹 Removed {removed_count} keywords from this group.",
            parse_mode="Markdown"
        )
        context.user_data.pop("remove_kw_data", None)

    elif data == "kw_remove_all":
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ CONFIRM REMOVE ALL", callback_data="kw_confirm_remove_all")],
            [InlineKeyboardButton("❌ Cancel", callback_data="kw_cancel_remove_all")]
        ])

        await query.edit_message_text(
            "🚨 *Danger Zone* 🚨\n\n"
            "You are about to remove ALL keywords from this group.\n\n"
            "❗ This action cannot be undone!",
            reply_markup=confirm_keyboard,
            parse_mode="Markdown"
        )

    elif data == "kw_confirm_remove_all":
        subscription_collection.update_one(
            {"user_id": user_id, "group_id": session["group_id"]},
            {"$set": {"keywords": []}}
        )
        await query.edit_message_text(
            "🧹 All keywords have been removed from this group.",
            parse_mode="Markdown"
        )
        context.user_data.pop("remove_kw_data", None)

    elif data == "kw_cancel_remove_all":
        await show_remove_menu(update, context)

