================================================================================
  VAULTFATHER - Personal Movie Hub & Encrypted Telegram Cloud Vault
================================================================================

Hey everyone! 

I built VaultFather because I got sick of three things:
1. Running out of local hard drive space and not wanting to pay $20/month for cloud storage.
2. Downloading a great movie only to find out the subtitles are missing or out of sync.
3. Boring, bloated media managers that look like spreadsheets instead of a cinema deck.

VaultFather turns Telegram into your personal, unlimited, encrypted cloud backup, 
wraps your movie collection in a dark Obsidian Glass spacecraft UI, and includes 
a Subtitles Studio that finds matching subs and losslessly remuxes them in 2 seconds.

Here is the quick no-BS guide on how to get it running, even if you are not a techie.


================================================================================
 [1] WHAT YOU NEED INSTALLED (THE 3 PREREQUISITES)
================================================================================

You need three free tools on your PC. I've placed 1-click download shortcuts 
right in this folder so you don't even have to google them:

1. PYTHON 3.10+ (Double-click "Python_Download.url")
   - Download the Windows installer and run it.
   - *** DO NOT SKIP THIS ***:
     On the very first screen of the installer, look at the bottom and CHECK:
     [X] "Add python.exe to PATH"
     If you forget this, Windows won't know where Python is when you run the app.

2. VLC MEDIA PLAYER (Double-click "VLC_Download.url")
   - VaultFather will happily play videos in WHATEVER media player you have 
     set as your Windows default (MPC-HC, MPV, PotPlayer, etc.).
   - HOWEVER, VLC is heavily recommended inside VaultFather.
     Why? Because in the Subtitles Studio, VLC lets VaultFather inject multiple 
     candidate subtitle tracks simultaneously so you can switch between them 
     with a right-click to test sync before baking them in.

3. 7-ZIP (Double-click "7Zip_Download.url")
   - Free, lightweight archiver.
   - VaultFather uses 7-Zip to split big 4K/1080p movies into 1.8 GB encrypted 
     chunks (AES-256) so Telegram never sees what you're uploading.
   - Just install it to the default C:\Program Files\7-Zip path. VaultFather 
     finds it automatically.

OPTIONAL: FFmpeg (For 0% Quality Loss Subtitle Remuxing)
   - If you want VaultFather to remux subtitles into your MKV/MP4 files losslessly, 
     install FFmpeg. The easiest way on Windows is opening PowerShell and running:
     `winget install Gyan.FFmpeg`


================================================================================
 [2] HOW TO LAUNCH (LITERALLY 1 CLICK)
================================================================================

1. Open the "VaultFather" folder.
2. Double-click "run_vaultfather.bat".
3. That's it! On the first launch, it will auto-install all Python dependencies 
   from requirements.txt. Once done, the full-screen command interface boots up.


================================================================================
 [3] GETTING YOUR FREE API KEYS (TAKES 3 MINUTES)
================================================================================

VaultFather doesn't cost a dime to run, but you need two free API keys:

--------------------------------------------------------------------------------
A. TELEGRAM API (api_id & api_hash)
--------------------------------------------------------------------------------
This allows VaultFather to talk to Telegram directly via MTProto at full ethernet speed.

1. Go to https://my.telegram.org in your browser.
2. Put in your phone number (with country code, e.g. +1 555 123 4567).
3. Telegram will ping you a confirmation code in your Telegram app. Enter it.
4. Click "API development tools".
5. Fill in:
   - App title: VaultFather
   - Short name: vaultfather
   - Platform: Desktop
6. Hit "Create application".
7. Boom! You'll see:
   - api_id: (a number)
   - api_hash: (a string of letters and numbers)
8. In VaultFather:
   - Click "Settings" (bottom-left gear icon).
   - Click "Connect Telegram Account", paste those two in, and log in. Done.

--------------------------------------------------------------------------------
B. TMDB API KEY (For Movie Posters, Ratings & Rotating 4K Backdrops)
--------------------------------------------------------------------------------
This gives you beautiful posters, movie plots, release years, and rotating 
4K backdrops from the TMDb Top 100 movies every 7 seconds.

1. Sign up for free at https://www.themoviedb.org/signup
2. Click your profile icon at top right -> "Settings" -> "API" on the left menu.
3. Click "Create" under Request an API Key -> choose "Developer".
4. Fill out the brief form (App Name: VaultFather, URL: https://github.com).
5. Copy your "API Key (v3 auth)".
6. In VaultFather Settings, paste it under "TMDb Poster & Metadata Key" and hit Save.


================================================================================
 [4] HOW BACKUPS & CLOUD VAULT WORK
================================================================================

1. Create a private channel in Telegram:
   - In Telegram, click New Message -> New Channel.
   - Name it whatever you want (e.g. "My Vault").
   - MAKE SURE IT IS SET TO PRIVATE.

2. In VaultFather:
   - Go to Settings -> "Destination Channels" -> click "+ Add Channel".
   - Pick your private channel from the list.

3. Backing Up a Movie:
   - Go to the "Movies" tab.
   - Click "+ Backup" on any movie card.
   - VaultFather splits the movie into encrypted 7z volumes with a randomized 
     AES-256 password, uploads it across parallel streams to your private channel, 
     and records the file message IDs into your local database.
   - Once backed up, you can safely delete the movie locally if you need space. 
     It will stay in your "Cloud" tab forever and can be restored or streamed in 1 click!


================================================================================
 [5] SUBTITLES STUDIO (NO QUALITY LOSS)
================================================================================

- Select any movie in the Subtitles tab.
- If you have an .srt file, drag and drop it into the box.
- Or hit "Find Subtitles" — VaultFather computes the exact 64-bit video hash 
  and checks OpenSubtitles for verified sync matches.
- Select candidate subtitles and hit "Preview in Player".
  (If you have VLC, it opens with all subtitles loaded so you can switch between 
  them live. If you use MPC-HC / MPV, it opens your default player).
- Once you know which sub matches best, select only that one and click "Run".
- VaultFather copies the video and audio streams bit-for-bit (`ffmpeg -c copy`).
  Zero re-encoding. 0% loss in video or audio quality. Takes ~2-5 seconds.


================================================================================
 [6] FAQ & COMMON HEADACHES
================================================================================

Q: "Python is not recognized as an internal or external command"
A: You installed Python without checking "Add to PATH". Re-run the Python 
   installer, click "Modify", and check "Add Python to environment variables / PATH".

Q: "Can I use MPC-HC, MPV, or PotPlayer instead of VLC?"
A: Yes! VaultFather opens your system's default media player. VLC is only 
   specifically recommended for the Subtitles Studio preview because VLC supports 
   loading multiple subtitle tracks at the same time via command-line.

Q: "Can Telegram see my movies or ban my account?"
A: No. Before uploading, VaultFather archives your files with 7-Zip AES-256 
   encryption and randomized passwords. To Telegram's servers, the uploads look 
   like generic binary data chunks (.7z.001, .7z.002).

Q: "Where are my passwords and login sessions saved?"
A: Strictly locally on your own computer inside `~/.vaultfather/`. Nothing 
   ever leaves your PC.

Enjoy your new movie station! If you like it, star the repo on GitHub!
================================================================================
