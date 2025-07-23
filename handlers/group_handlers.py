from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.connection import get_db
import hashlib
from collections import defaultdict
from datetime import datetime

db = get_db()
group_collection = db["bot_groups"]
subscription_collection = db["user_subscriptions"]

def get_group_display_name(group_id, group_name, all_groups):
    """Generate display name that handles duplicates with better user context"""
    same_name_groups = [g for g in all_groups if g["group_name"] == group_name]
    
    if len(same_name_groups) == 1:
        return group_name
    else:
        same_name_groups.sort(key=lambda x: x["group_id"])
        group_index = next((i for i, g in enumerate(same_name_groups) if g["group_id"] == group_id), 0)
        
        ordinals = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"]
        if group_index < len(ordinals):
            return f"{group_name} ({ordinals[group_index]})"
        else:
            return f"{group_name} (#{group_index + 1})"

async def bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added to group"""
    member = update.my_chat_member
    chat = member.chat
    group_id = chat.id
    group_name = chat.title
    chat_type = chat.type

    if member.new_chat_member.status == "member":
        # Bot was added to group
        existing = group_collection.find_one({"group_id": group_id})
        if not existing:
            await cleanup_potential_migration_duplicates(group_name, group_id, context)
            # Immediately fetch latest chat info for accurate privacy
            chat_info = await context.bot.get_chat(group_id)
            group_collection.insert_one({
                "group_id": group_id,
                "group_name": chat_info.title,
                "chat_type": chat_info.type,
                "is_private": chat_info.username is None,
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow()
            })
            print(f"Bot added to new group: {group_name} ({group_id})")
        else:
            # Update existing group info in case of re-addition
            chat_info = await context.bot.get_chat(group_id)
            group_collection.update_one(
                {"group_id": group_id},
                {"$set": {
                    "group_name": chat_info.title,
                    "chat_type": chat_info.type,
                    "is_private": chat_info.username is None,
                    "last_updated": datetime.utcnow()
                }}
            )
            print(f"Bot re-added to existing group: {group_name} ({group_id})")
    
    elif member.new_chat_member.status in ["left", "kicked"]:
        # Bot was removed from group - clean up
        print(f"Bot removed from group: {group_name} ({group_id})")
        
        group_collection.delete_one({"group_id": group_id})
        result = subscription_collection.delete_many({"group_id": group_id})
        print(f"Cleaned up {result.deleted_count} subscriptions for removed group")

# ENHANCED: Migration handler with better detection
async def handle_migration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group migration (group -> supergroup conversion)"""
    if update.message and update.message.migrate_to_chat_id:
        old_id = update.message.chat_id
        new_id = update.message.migrate_to_chat_id

        print(f"Group migration detected: {old_id} -> {new_id}")

        # Get old group data
        old_group = group_collection.find_one({"group_id": old_id})
        if old_group:
            # Check if new group already exists (shouldn't happen but safety check)
            existing_new = group_collection.find_one({"group_id": new_id})
            if existing_new:
                print(f"New group {new_id} already exists - merging data")
                # Merge subscription data and remove old group
                subscription_collection.update_many(
                    {"group_id": old_id},
                    {"$set": {"group_id": new_id}}
                )
                group_collection.delete_one({"group_id": old_id})
                return

            # Fetch latest chat info for new group
            chat_info = await context.bot.get_chat(new_id)
            new_group_data = old_group.copy()
            new_group_data["group_id"] = new_id
            new_group_data["group_name"] = chat_info.title
            new_group_data["chat_type"] = chat_info.type
            new_group_data["is_private"] = chat_info.username is None
            new_group_data["migrated_from"] = old_id
            new_group_data["migrated_at"] = datetime.utcnow()
            new_group_data["last_updated"] = datetime.utcnow()

            # Insert new group
            group_collection.insert_one(new_group_data)

            # Update all user subscriptions
            result = subscription_collection.update_many(
                {"group_id": old_id},
                {"$set": {"group_id": new_id}}
            )

            # Delete old group record
            group_collection.delete_one({"group_id": old_id})

            print(f"Migration completed: Updated {result.modified_count} subscriptions")

# NEW: Periodic health check to catch missed updates
async def periodic_group_health_check(context: ContextTypes.DEFAULT_TYPE):
    """
    Periodic check to ensure all tracked groups are still accessible
    and update their information if needed
    """
    all_groups = list(group_collection.find({}))
    updated_count = 0
    removed_count = 0
    
    for group in all_groups:
        group_id = group["group_id"]
        
        try:
            # Try to get current chat info
            chat_info = await context.bot.get_chat(group_id)
            
            # Check if group info needs updating
            updates = {}
            
            if group["group_name"] != chat_info.title:
                updates["group_name"] = chat_info.title
            
            if group.get("is_private", True) != (chat_info.username is None):
                updates["is_private"] = chat_info.username is None
            
            if group.get("chat_type") != chat_info.type:
                updates["chat_type"] = chat_info.type
            
            # Update if changes found
            if updates:
                updates["last_updated"] = datetime.utcnow()
                group_collection.update_one(
                    {"group_id": group_id},
                    {"$set": updates}
                )
                
                # Update subscriptions if name changed
                if "group_name" in updates:
                    subscription_collection.update_many(
                        {"group_id": group_id},
                        {"$set": {"group_name": updates["group_name"]}}
                    )
                
                updated_count += 1
                print(f"Health check updated group {group_id}: {updates}")
                
        except Exception as e:
            # Group is no longer accessible - remove it
            print(f"Group {group_id} ({group['group_name']}) is orphaned: {e}")
            
            group_collection.delete_one({"group_id": group_id})
            result = subscription_collection.delete_many({"group_id": group_id})
            removed_count += 1
            
            print(f"Removed orphaned group and {result.deleted_count} subscriptions")
    
    if updated_count > 0 or removed_count > 0:
        print(f"Health check completed: {updated_count} updated, {removed_count} removed")
    
    return {"updated": updated_count, "removed": removed_count}

# NEW: Force refresh single group
async def force_refresh_group(group_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Force refresh a single group's information"""
    try:
        chat_info = await context.bot.get_chat(group_id)
        
        updates = {
            "group_name": chat_info.title,
            "is_private": chat_info.username is None,
            "chat_type": chat_info.type,
            "last_updated": datetime.utcnow()
        }
        
        group_collection.update_one(
            {"group_id": group_id},
            {"$set": updates},
            upsert=True
        )
        
        # Update subscriptions with new name
        subscription_collection.update_many(
            {"group_id": group_id},
            {"$set": {"group_name": updates["group_name"]}}
        )
        
        print(f"Force refreshed group {group_id}")
        return True
        
    except Exception as e:
        print(f"Failed to refresh group {group_id}: {e}")
        return False

async def cleanup_potential_migration_duplicates(group_name, new_group_id, context):
    """Check for and clean up groups that might be old versions of migrated groups"""
    same_name_groups = list(group_collection.find({"group_name": group_name}))
    
    if len(same_name_groups) > 0:
        print(f"Found {len(same_name_groups)} existing groups with name '{group_name}'")
        
        groups_to_remove = []
        
        for group in same_name_groups:
            old_group_id = group["group_id"]

            # IMPORTANT: If it's the same group ID, don't treat it as a duplicate
            # This happens when group privacy changes trigger bot re-addition
            if old_group_id == new_group_id:
                print(f"Skipping same group ID {old_group_id} - this is a privacy/settings change")
                continue
            
            try:
                chat_info = await context.bot.get_chat(old_group_id)
                print(f"Group {old_group_id} is still accessible")
            except Exception as e:
                print(f"Group {old_group_id} is no longer accessible: {e}")
                groups_to_remove.append(old_group_id)
        
        # Remove inaccessible groups and transfer their subscriptions
        for old_group_id in groups_to_remove:
            print(f"Migrating subscriptions from {old_group_id} to {new_group_id}")
            
            subscription_collection.update_many(
                {"group_id": old_group_id},
                {"$set": {"group_id": new_group_id}}
            )
            
            group_collection.delete_one({"group_id": old_group_id})
            print(f"Removed orphaned group {old_group_id}")

# Rest of your existing code (list_groups, group_detail, etc.) remains the same...
GROUPS_PER_PAGE = 5

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    user_id = update.effective_user.id
    all_groups = list(group_collection.find({}))
    user_subs = list(subscription_collection.find({"user_id": user_id}))
    sub_map = {sub["group_id"]: sub for sub in user_subs}

    if not all_groups:
        if update.message:
            await update.message.reply_text(
                "😕 No active groups found.\n\nYou need to be in at least one group *with the bot added*.",
                parse_mode="Markdown"
            )

    total_pages = (len(all_groups) - 1) // GROUPS_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))

    start = page * GROUPS_PER_PAGE
    end = start + GROUPS_PER_PAGE
    paginated_groups = all_groups[start:end]

    message = (
        "📋 *Your Groups*\n\n"
        "These are the groups you and the bot are part of.\n\n"
        "🟢 Tracking – You'll receive notifications for matching keywords\n"
        "🔴 Muted – Notifications are turned off for this group\n"
        "⚪️ Not Tracking – You haven't enabled keyword alerts for this group\n\n"
    )

    buttons = []

    for group in paginated_groups:
        group_id = group["group_id"]
        status = "⚪️ Not Tracking"
        if group_id in sub_map:
            subscribed = sub_map[group_id].get("subscribed", False)
            status = "🟢 Tracking" if subscribed else "🔴 Muted"

        display_name = get_group_display_name(group_id, group["group_name"], all_groups)
        privacy_icon = "🔒" if group.get("is_private", True) else "🌐"
        button_text = f"{privacy_icon} {display_name} - {status}"
        
        buttons.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"group_{group_id}"
            )
        ])

    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"group_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ View more groups", callback_data=f"group_page_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    # Add refresh button
    buttons.append([InlineKeyboardButton("🔄 Refresh Groups", callback_data="refresh_groups")])

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
    elif update.message:
        await update.message.reply_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def group_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed group options with enhanced info"""
    query = update.callback_query
    await query.answer()
    
    group_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    group = group_collection.find_one({"group_id": group_id})
    sub = subscription_collection.find_one({"user_id": user_id, "group_id": group_id})

    if not group:
        await query.answer("❌ Group not found!", show_alert=True)
        return

    all_groups = list(group_collection.find({}))
    display_name = get_group_display_name(group_id, group["group_name"], all_groups)

    if sub:
        subscribed = sub.get("subscribed", False)
        status = "🟢 Tracking" if subscribed else "🔴 Muted"
        keyword_count = len(sub.get("keywords", []))
    else:
        subscribed = None
        status = "⚪️ Not Tracking"
        keyword_count = 0

    privacy_icon = "🔒 Private" if group.get("is_private", True) else "🌐 Public"
    
    # Show last updated time for debugging
    last_updated = group.get("last_updated", group.get("created_at"))
    last_updated_str = last_updated.strftime("%Y-%m-%d %H:%M") if last_updated else "Unknown"
    
    group_info = (
        f"⚙️ *{display_name}*\n"
        f"Status: {status}\n"
        f"Type: {privacy_icon}\n"
        f"Keywords: {keyword_count}\n"
        f"Last Updated: {last_updated_str}\n"
        f"Group ID: `{group_id}`"
    )

    buttons = []

    if subscribed is True:
        buttons.append([InlineKeyboardButton("🔇 Mute Notifications", callback_data=f"mute_{group_id}")])
    elif subscribed is False:
        buttons.append([InlineKeyboardButton("🔔 Enable Notifications", callback_data=f"join_{group_id}")])
    else:
        buttons.append([InlineKeyboardButton("➕ Start Tracking", callback_data=f"join_{group_id}")])

    if sub:
        buttons.append([InlineKeyboardButton("🚪 Leave Group", callback_data=f"leave_{group_id}")])

    buttons.append([InlineKeyboardButton("🔄 Refresh Info", callback_data=f"refresh_{group_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back to List", callback_data="back_to_groups")])
    
    await query.edit_message_text(
        group_info,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

async def handle_group_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data == "back_to_groups":
        await list_groups(update, context)
        return

    if data == "refresh_groups":
        await query.answer("🔄 Refreshing groups...")
        result = await periodic_group_health_check(context)
        await list_groups(update, context)
        return

    if data.startswith("refresh_"):
        group_id = int(data.split("_")[1])
        await query.answer("🔄 Refreshing group info...")
        success = await force_refresh_group(group_id, context)
        if success:
            await group_detail(update, context)
        else:
            await query.answer("❌ Failed to refresh group info", show_alert=True)
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
        
        if not group:
            await query.answer("❌ Group not found!", show_alert=True)
            return
            
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