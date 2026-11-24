# Set up Google sign-in (your own client ID)

Yappr's **Connect Google Calendar** button needs a Google Cloud "client ID". It tells Google which app is asking. Until Yappr ships with one that Google has reviewed, you make your own. It's free and takes about 10 minutes. You only do it once.

You'll need a Google account. Any Gmail account works.

## 1. Make a project

1. Go to <https://console.cloud.google.com/projectcreate>.
2. **Project name:** `Yappr`. Click **Create**, and make sure the new project is selected at the top of the page.

## 2. Turn on the Calendar API

1. Go to <https://console.cloud.google.com/apis/library/calendar-json.googleapis.com>.
2. Click **Enable**.

## 3. Set up the sign-in screen

1. Go to <https://console.cloud.google.com/auth/overview> and click **Get started**.
2. **App name:** `Yappr`. **User support email:** yours. Click **Next**.
3. **Audience:** **External**. Click **Next**.
4. **Contact information:** your email. Click **Next**, agree to the policy, and click **Create**.
5. Open **Audience** in the left menu. Under **Test users**, click **Add users** and add your own Gmail address (and anyone else who'll try it, up to 100).
6. Open **Data access** → **Add or remove scopes**. Tick `.../auth/calendar.events.readonly` (search for "calendar.events.readonly"). Then click **Update** and **Save**.

## 4. Make the client ID

1. Go to <https://console.cloud.google.com/auth/clients> and click **Create client**.
2. **Application type:** **Desktop app**. **Name:** `Yappr desktop`. Click **Create**.
3. Click **Download JSON**. You get a file called something like `client_secret_….json`.

## 5. Give it to Yappr

Rename the file to `google-client.json` and put it in `%LOCALAPPDATA%\Yappr\` (paste that into File Explorer's address bar). Restart Yappr from the tray icon. **Settings → Meetings** now shows **Connect Google Calendar**.

Don't commit that file to git. `.gitignore` already skips it, and the pre-commit scan blocks it.

## What to expect while it's in "Testing"

- Google shows a **"Google hasn't verified this app"** screen. Click **Continue**. That's expected for your own test project.
- In Testing mode Google ends the sign-in after **7 days**, and Yappr says *"Google stopped accepting Yappr's sign-in"*. Click **Connect** again. Publishing the app (below) removes this limit.

## Later: making it work for everyone

To let anyone who installs Yappr click Connect without their own client ID, the project has to go through Google's review:

- **Audience → Publish app** (moves it out of Testing).
- **Branding:** a homepage and a privacy policy page (GitHub Pages works), and the authorized domain they're on.
- **Verification** for the sensitive calendar scope: a short screen recording of the sign-in and where calendar data shows up in Yappr, plus why it's needed. Calendar read-only is "sensitive", not "restricted", so there's no paid security assessment. It usually takes a few weeks.

Once it's approved, the `google-client.json` goes into `yappr/assets/` (with an exception for that one path in `tools/scan_history.py`), and every copy of Yappr uses it. Your own file in `%LOCALAPPDATA%\Yappr` still wins if you have one.
