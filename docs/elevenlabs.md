# ElevenLabs voice (optional)

Clock speaks with free edge-tts by default. ElevenLabs Eleven v4 sounds more expressive and understands audio tags
such as `[whispers]` or `[laughs]`, but it needs internet and spends credits. Clock falls back to edge-tts whenever
ElevenLabs fails, so she always speaks.

## Turn it on
1. Create an API key at elevenlabs.io (Developers > API keys). Give it Text to Speech access. Add "User: read" if you
   want `--check` to show your balance.
2. In `.env` (git-ignored):

       ELEVENLABS_API_KEY=sk_...
       CLOCK_TTS=eleven
       CLOCK_ELEVEN_VOICE=<voice id from your ElevenLabs voice library>

3. Run `python -m clock --check`. The ElevenLabs line shows the model, your remaining monthly budget and balance.

## Settings
| Variable | Default | Meaning |
|---|---|---|
| `CLOCK_TTS` | `edge` | `edge` or `eleven` |
| `CLOCK_ELEVEN_MODEL` | `eleven_v4_turbo` | `eleven_v4` is higher quality; `eleven_v4_turbo` answers faster (better for conversation) |
| `CLOCK_ELEVEN_VOICE` | `JBFqnCBsd6RMkjVDRZzb` | voice id |
| `CLOCK_ELEVEN_MAX_CHARS` | `400` | longer sentences use edge-tts |
| `CLOCK_ELEVEN_BUDGET` | `8000` | characters per calendar month; the free plan has 10,000 credits. Over it, edge-tts takes over until next month |

The budget counter is `~/clock_eleven_usage.json`. It counts characters Clock sent; ElevenLabs' own balance is the truth.

## What happens when something goes wrong
- Key rejected (401/403) or no credits (402): ElevenLabs is switched off until Clock restarts; one message is printed.
- Rate limited (429): only that sentence uses edge-tts.
- Network error or server error: that sentence uses edge-tts; after 3 in a row ElevenLabs is switched off for the session.
- The key is sent only in the `xi-api-key` header and is never printed or logged.

## Audio tags
With `CLOCK_TTS=eleven`, the system prompt lets her use at most one tag per reply, at the start, where it fits.
Tags are removed from the screen, the panel, the phone and the edge-tts fallback, so you never see or hear "bracket whispers".
SSML such as `<break>` does not work with v4.
