# Talk to Clock from your phone (Telegram)

Clock polls a private Telegram bot. It only makes outgoing HTTPS requests, so no port is opened on your PC or router.
The PC has to be on, with Clock running, for the phone to get an answer.

## Setup (5 minutes)
1. In Telegram, open **@BotFather**, send `/newbot`, pick a name. Copy the token it gives you.
2. Add it to `.env` (git-ignored): `CLOCK_TELEGRAM_TOKEN=123456:ABC...`
3. Find your chat id: run `python -m clock.remote`, then send any message to your new bot from your phone.
   It prints `CLOCK_TELEGRAM_CHAT=<number>`. Add that line to `.env`.
4. Start Clock. It prints `(phone: Telegram on, 1 chat(s), tools: safe)`. Message the bot a request.

Without both the token and your chat id, the phone channel stays off.

## What it does
- Your message is answered like a typed request. The reply comes back as text.
- Reminders, routines and finished background tasks are also sent to your phone, not only spoken on the PC.
- Messages sent while Clock was off are **ignored** on startup (you get a note saying how many), so an old
  "lock the PC" can never run later. Messages older than 2 minutes are dropped too.

## Safety
- Only your chat id is answered. Anyone else who finds the bot gets no reply at all. Group chats are ignored.
- Keep the token secret. Anyone with it can read your bot's messages. If it leaks, `/revoke` it in BotFather.
- Telegram is not end-to-end encrypted for bots: messages pass through Telegram's servers. Don't send secrets.
- Default `CLOCK_REMOTE_TOOLS=safe`: from the phone Clock **cannot** open or close apps, open links, use the clipboard,
  control or lock windows, or look at your screen or webcam, and any "are you sure?" is refused. It can answer
  questions, search the web, set reminders/timers/routines, take notes, remember facts, run background research and
  change the volume. Set `CLOCK_REMOTE_TOOLS=all` only if you accept that anyone who gets into your Telegram account
  can control the PC.
- Every phone request is logged in `~/clock_audit.jsonl` with `"source": "phone"`.

## Troubleshooting
- No reply: check `klock.log` for `(Telegram ... failed: ...)` lines. `HTTP 401` means a wrong token; `HTTP 409` means
  another program is polling the same bot (stop it, or make a second bot).
- It answers on the PC but not on the phone: your chat id in `.env` does not match. Re-run `python -m clock.remote`.
