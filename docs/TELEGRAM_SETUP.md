# Telegram Ingestion Bot Setup

## 1) Create a bot with BotFather
1. Open Telegram and start a chat with **@BotFather**.
2. Send `/newbot` and follow prompts.
3. Copy the HTTP API token BotFather provides.

## 2) Set the TELEGRAM_BOT_TOKEN on Windows (PowerShell)
```powershell
$env:TELEGRAM_BOT_TOKEN = "<your_bot_token_here>"
```
To persist for future sessions:
```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "<your_bot_token_here>", "User")
```

## 3) Allowlist your chat ID and retrieve it
The bot only responds to allowlisted chat IDs stored at:
`D:\LabelOps\config\telegram_allowlist.json`

1. Open the JSON file and add your chat ID under `allowed_chat_ids`.
2. If you do not know your chat ID yet, temporarily add any placeholder (or an empty list) and then:
   - Send a message to the bot.
   - Update the file to include your chat ID once you receive it from an admin.
3. Once allowlisted, send `/chatid` to the bot and it will reply with your chat ID.

Example:
```json
{
  "allowed_chat_ids": [123456789],
  "default_client_by_chat": {
    "123456789": "client_01"
  }
}
```

## 4) Routing rules (client selection)
- If the **first non-empty line** of your message is `client_01`, `client_02`, etc., the bot routes to that client and removes the line from the content.
- Otherwise, if your chat ID has a default client in `telegram_allowlist.json`, the bot uses that.
- If neither applies, it falls back to `client_01`.

Example message:
```
client_02
John Smith
123 Example St
Austin, TX 78701
```

## 5) Common issues
- **Bot privacy mode**: If the bot is in a group and privacy mode is on, it might not receive messages. Disable privacy mode in BotFather or use a direct chat.
- **Group permissions**: Ensure the bot has permission to read messages in the group.
- **Message not saved**: Only allowlisted chat IDs are processed. Check `telegram_allowlist.json`.
- **Media rejected**: The bot only accepts plain text. Send addresses as text.
