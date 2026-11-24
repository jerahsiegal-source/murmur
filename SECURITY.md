# Security

## Your API key

Yappr is "bring your own key". Here is exactly what happens to it.

**Where it's stored.** When you click **Save** in Settings, the key goes to **Windows Credential Manager**, the same vault Windows uses for saved network passwords. Windows encrypts it with your Windows sign-in. There is one entry per provider (`Yappr / anthropic-api-key`, `Yappr / llm-api-key`). The key is never written to `settings.json`, the logs, the history, the cost log or anywhere in this repository. To see or remove it: Start → **Credential Manager** → **Windows Credentials** → entries starting with `Yappr`.

**Where it's sent.** Only to the AI provider you picked, in the request header:

- Claude: `https://api.anthropic.com`, through Anthropic's official SDK.
- OpenAI-compatible: the **Base URL** you set. It must start with `https://`. Plain `http://` is allowed only for `localhost`, for a model server running on your own computer. Yappr refuses to follow redirects with your key attached.

There is no Yappr server and no telemetry. Yappr never sends your key anywhere else.

**What's logged.** Errors are logged without the key. The cost log (`usage.jsonl`) records token counts and prices only.

**Environment variables (optional, for scripts).** `YAPPR_ANTHROPIC_API_KEY` overrides the stored Claude key, and `YAPPR_API_KEY` overrides the stored OpenAI-compatible key. Each one is used only for its own provider.

### What this can't protect against

Credential Manager is tied to your Windows account. Any program running as you can read it, including malware you've already installed. That's true of every desktop app that remembers a key. Two habits matter more than anything Yappr can do:

1. **Set a spending limit** in your provider's console (Anthropic and OpenAI both offer monthly limits). Then even a stolen key can only cost you a set amount.
2. **Use a key just for Yappr**, so you can revoke it without breaking anything else.

If you think a key has leaked, **revoke it in your provider's console** and create a new one. Deleting it from a file or from git history does not make a leaked key safe again.

## Google Calendar sign-in

Only if you click **Connect Google Calendar**. Code: `yappr/google_auth.py`.

- **What Yappr can do:** read your calendar events (`calendar.events.readonly`) and see your email address (`openid email`). It can't change your calendar, and can't see your mail, Drive or anything else.
- **How you sign in:** in your normal browser, on Google's own page, never inside the Yappr window. Google sends the browser back to `http://127.0.0.1:<random port>` on your own PC. A random `state` value and PKCE make sure only the Yappr that started the sign-in can finish it.
- **Where it's stored:** the long-lived sign-in (the "refresh token") goes to Windows Credential Manager as `Yappr / google-refresh-token`. Short-lived access tokens stay in memory. Neither is written to `settings.json`, the log or anywhere else. `settings.json` holds only your email address, so Settings can show who's connected.
- **Where it's sent:** only to `oauth2.googleapis.com` (sign-in) and `www.googleapis.com` (Calendar). Redirects are refused.
- **What leaves your PC because of it:** nothing new goes to Google. From the events, attendee *names* go to your AI service with the meeting transcript so it spells them right. Email addresses never do.
- **Turning it off:** **Disconnect** cancels the access at Google and deletes the token. You can also remove Yappr at [myaccount.google.com/connections](https://myaccount.google.com/connections). That works even if Yappr is gone.

The "client ID" in `google-client.json` identifies the app to Google, not you. Google says the "client secret" in a desktop app's client file isn't a real secret. The same Credential Manager caveats as for the API key apply to the Google token (see below).

## Forks and downloads

Yappr is open source, so anyone can publish a modified copy. A modified copy can send your key anywhere, and no app can prevent that. Install from the official repository, or read the changes before you trust a fork with a key. The key handling is all in `yappr/config.py` (storage) and `yappr/llm.py` (sending).

## For contributors

- Never commit keys, `.env` files, recordings or anything from `%LOCALAPPDATA%\Yappr`. `.gitignore` already excludes the usual ones.
- Turn on the pre-commit secret scan once per clone. It blocks a commit that would add a key, a private calendar link, an email address, a Windows user path or a recording:

  ```powershell
  git config core.hooksPath .githooks
  ```

- GitHub Actions runs the same scan over the whole git history on every push and pull request (`.github/workflows/secret-scan.yml`). You can run it yourself with `python tools/scan_history.py`.

## Reporting a vulnerability

Please don't open a public issue for a security problem. Use GitHub's **Report a vulnerability** button on the repository's Security tab, so it can be fixed before it's public.
