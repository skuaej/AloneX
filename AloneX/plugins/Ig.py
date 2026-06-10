import re
import os
import asyncio
import time
from pyrogram import filters
from yt_dlp import YoutubeDL
from AloneX import app

# --- GLOBAL VARIABLES ---
INSTAGRAM_REGEX = r".*(instagram.com|instagr.am)/(p|reel|tv|share)/[^\s]+"

# --- UTILITIES ---
def download_ig_video(url):
    os.makedirs("downloads", exist_ok=True)
    vid_id = str(int(time.time()))
    out_file = f"downloads/ig_{vid_id}.mp4"
    
    # Pure yt-dlp setup (NO COOKIES, NO EXTERNAL APIs)
    ydl_opts = {
        'format': 'best',
        'outtmpl': out_file,
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        }
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            caption = info.get('description') or info.get('title') or 'Instagram Video'
            uploader = info.get('uploader') or 'Instagram User'
            
            return out_file, caption, uploader
    except Exception as e:
        return None, str(e), None

# --- HANDLER ---
@app.on_message(filters.text & filters.regex(INSTAGRAM_REGEX) & ~app.bl_users)
async def auto_detect_instagram_link(client, message):
    match = re.search(r'(https?://[^\s]+)', message.text)  
    if not match: 
        return  
          
    url = match.group(1)
    status_msg = await message.reply_text("⚡ **Link detected!** Processing with yt-dlp...")  
    
    loop_engine = asyncio.get_running_loop()  

    # Run yt-dlp download in background
    file_path, caption_text, uploader = await loop_engine.run_in_executor(
        None, download_ig_video, url
    )  
    
    if not file_path or not os.path.exists(file_path):
        # file_path holds the error message if it fails
        error_msg = caption_text[:200] if caption_text else "Unknown yt-dlp error"
        return await status_msg.edit(f"❌ **Extraction Failed!** Instagram blocked the request.\n\n`{error_msg}`")

    final_caption = (  
        f"⚡ **Instagram Reel Downloaded** ⚡\n\n"  
        f"👤 **Uploader :** @{uploader}\n"  
        f"📝 **Caption :** {caption_text[:180]}...\n"  
    )  

    await status_msg.edit("📤 **Uploading Video to Telegram...**")  
    
    try:
        await message.reply_video(  
            video=file_path,   
            caption=final_caption
        )  
        await status_msg.delete()  
    except Exception as e:
        await status_msg.edit(f"❌ Upload failed: {e}")
    finally:
        if os.path.exists(file_path):  
            os.remove(file_path)  

__MODULE__ = "Iɴsᴛᴀɢʀᴀᴍ"
__HELP__ = """
ℹ️ **Instagram Auto Downloader**:
Paste any Instagram link (reel, post, tv). The bot will use yt-dlp to download it directly.
"""
