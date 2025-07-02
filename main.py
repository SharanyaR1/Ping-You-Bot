from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, filters
from handlers.group_handlers import list_groups, group_detail, handle_group_actions, bot_added
from handlers.keyword_handlers import use_group, handle_use_button, add_keyword, list_keywords, remove_keyword, handle_remove_callback,show_remove_menu
from handlers.message_handlers import handle_group_message
from handlers.utility_handlers import start, help_command, keywords_overview, reset_command, handle_reset_callback, handle_keyword_page_nav
from config import BOT_TOKEN

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Group monitoring
    app.add_handler(ChatMemberHandler(bot_added))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_message))

    # Group management
    app.add_handler(CommandHandler("groups", list_groups))
    app.add_handler(CallbackQueryHandler(handle_group_actions, pattern="^(group|join|mute|leave)"))
    app.add_handler(CallbackQueryHandler(handle_group_actions, pattern="^back_to_groups$"))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CallbackQueryHandler(handle_reset_callback, pattern="^(confirm|cancel)_reset$"))

    # Keyword management
    app.add_handler(CommandHandler("use", use_group))
    app.add_handler(CallbackQueryHandler(handle_use_button, pattern="^use\\|"))
    app.add_handler(CommandHandler("add", add_keyword))
    app.add_handler(CommandHandler("list", list_keywords))
    app.add_handler(CommandHandler("remove", remove_keyword))
    app.add_handler(CallbackQueryHandler(handle_remove_callback, pattern="^kw_"))
    app.add_handler(CommandHandler("keywords", keywords_overview))
    app.add_handler(CallbackQueryHandler(handle_keyword_page_nav, pattern="^kwpage_"))

    # Help commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()