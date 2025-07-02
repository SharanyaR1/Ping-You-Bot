# 🤖 PingYou Bot

PingYou is a Telegram bot that helps users **track keywords in real time across multiple Telegram groups**. Users can subscribe to groups, manage keywords, mute/unmute notifications, and receive alerts in their personal chat whenever relevant messages are posted.


## Features

- Real-time keyword tracking in groups
- Personalized notifications
- Group-specific keyword lists per user
- Subscribe / Mute / Leave group functionality
- Designed for minimal noise, alerts are user-controlled
- MongoDB-based storage

## Demo

> Try it live: [@pingyou_bot](https://t.me/pingyou_bot)  
> *(You must be in at least one group where the bot is added)*


## Tech Stack

- **Python 3.10+**
- [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) (v20+)
- **MongoDB** (for user/group/keyword storage)
- **Vultr** (Linux-based deployment)

## Usage

Interact with the bot by sending the following commands in **private chat**:

| Command           | Description                                                                 |
|------------------|-----------------------------------------------------------------------------|
| `/groups`        | View and manage all Telegram groups you and the bot are part of. Subscribe, mute, or leave tracking per group. |
| `/use`           | Select a group to manage its keyword list. This is a prerequisite for `/add`, `/list`, and `/remove`. |
| `/add <keyword>` | Add a new keyword to track for the currently selected group.                |
| `/add <keyword1>,<keyword2>` | Add multiple keywords to track for the currently selected group.                |
| `/list`          | Show all keywords you are tracking for the selected group.                  |
| `/remove`        | Remove one or more keywords with inline button selection.                   |
| `/keywords`      | View all keywords you’re tracking across all groups with pagination.        |
| `/reset`         | Remove all tracked keywords for all groups. **Caution:** this cannot be undone. |
| `/help`          | Get a guide on how to use the bot and available features.                   |

> 📝 *Note: These commands must be used in a private chat with the bot, not inside group chats.*

## Thank You

Thank you for checking out **PingYou Bot**!  
If you have any feedback, suggestions, or questions, feel free to reach out or open an issue.