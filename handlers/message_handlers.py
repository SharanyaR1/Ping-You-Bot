from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, filters
from database.connection import get_db

db = get_db()
subscription_collection = db["user_subscriptions"]
group_collection = db["bot_groups"]

async def handle_group_message(update, context):
    """
    Unified handler that processes both metadata updates and message monitoring
    in a single pass for better efficiency
    """
    print("📩 Message received in group!")
    
    # 🔄 STEP 1: Handle real-time metadata updates first
    await handle_real_time_metadata_updates(update, context)
    
    # 🔄 STEP 2: Process message for keyword matching
    await process_keyword_matching(update, context)

async def handle_real_time_metadata_updates(update, context):
    """Handle all real-time group metadata updates"""
    chat = update.effective_chat
    
    # Only process group chats
    if chat.type not in ['group', 'supergroup']:
        return
    
    # Check if this is a metadata-changing event
    if not should_sync_metadata(update):
        return
    
    group_id = chat.id
    current_group = group_collection.find_one({"group_id": group_id})
    
    if not current_group:
        # Group not tracked - add it
        print(f"[RealTime] Found untracked group: {chat.title} ({group_id})")
        group_collection.insert_one({
            "group_id": group_id,
            "group_name": chat.title or "Unknown Group",
            "chat_type": chat.type,
            "is_private": chat.username is None,
            "created_at": datetime.utcnow(),
            "last_updated": datetime.utcnow(),
            "discovered_via": "real_time_update"
        })
        return
    
    # Check for changes and update
    updates = {}
    changes_detected = False
    
    # Check group name change
    if current_group["group_name"] != chat.title:
        print(f"[RealTime] Group name changed: {current_group['group_name']} -> {chat.title}")
        updates["group_name"] = chat.title
        changes_detected = True
    
    # Check privacy change
    current_privacy = chat.username is None
    if current_group.get("is_private", True) != current_privacy:
        privacy_status = "private" if current_privacy else "public"
        print(f"[RealTime] Group privacy changed to: {privacy_status}")
        updates["is_private"] = current_privacy
        changes_detected = True
    
    # Check chat type change
    if current_group.get("chat_type") != chat.type:
        print(f"[RealTime] Chat type changed: {current_group.get('chat_type')} -> {chat.type}")
        updates["chat_type"] = chat.type
        changes_detected = True
    
    # Apply updates if changes detected
    if changes_detected:
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
        
        print(f"[RealTime] Updated group {group_id} with: {updates}")

async def process_keyword_matching(update, context):
    """Process message for keyword matching (existing logic)"""
    if not update.message or not update.message.text:
        return

    message_text = update.message.text.lower()
    group_id = update.effective_chat.id
    group_name = update.effective_chat.title or "Unknown Group"
    
    print(f"🔍 Processing message: '{message_text}'")
    print(f"📍 Group ID: {group_id}")
    print(f"📍 Group Name: {group_name}")

    # Your existing keyword matching logic here...
    cursor = subscription_collection.find({"group_id": group_id, "subscribed": True})
    
    matched_any = False
    for doc in cursor:
        user_id = doc["user_id"]
        keywords = doc.get("keywords", [])
        
        matched_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in message_text:
                matched_keywords.append(kw)

        if matched_keywords:
            matched_any = True
            print(f"🎯 MATCHED KEYWORDS: {matched_keywords} for user {user_id}")
            
            try:
                # Your existing notification logic...
                highlighted = message_text
                for kw in matched_keywords:
                    highlighted = highlighted.replace(kw.lower(), f"*{kw.lower()}*")

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
                stored_group_name = doc.get('group_name', group_name)

                msg = (
                    f"📌 *Keyword Match!*\n"
                    f"🔍 *Matched:* {', '.join(f'`{kw}`' for kw in matched_keywords)}\n"
                    f"👤 *Sender:* {sender_name} {sender_username}\n"
                    f"👥 *Group:* `{stored_group_name}`\n"
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
                print(f"❌ Failed to forward to user {user_id}: {e}")

def should_sync_metadata(update) -> bool:
    """Only sync on group name changes"""
    return update.message and update.message.new_chat_title

 