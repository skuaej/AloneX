import re
import os
import asyncio
import time
import requests
from pyrogram import filters
from yt_dlp import YoutubeDL
from AloneX import app

# --- GLOBAL VARIABLES & STATE TRACKING ---
INSTAGRAM_REGEX = r".*(instagram.com|instagr.am)/(p|reel|tv|share)/[^\s]+"
current_status_msg = None
last_edit_time = 0

# --- UTILITIES ---
def create_progress_bar(percentage):
    total_blocks = 10
    filled_blocks = int(percentage / 10)
    empty_blocks = total_blocks - filled_blocks
    return f"[{'⬛' * filled_blocks}{'⬜' * empty_blocks}] {percentage}%"

def yt_dlp_callback(d):
    global current_status_msg, last_edit_time
    if d['status'] == 'downloading' and current_status_msg:
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)

        if total:  
            percentage = int((downloaded / total) * 100)  
            bar = create_progress_bar(percentage)  
            speed = d.get('speed', 0)  
            speed_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed else "Scraping Audio..."  
              
            now = time.time()  
            if now - last_edit_time > 2.0:  
                last_edit_time = now  
                try:  
                    loop = app.loop or asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(  
                        current_status_msg.edit(  
                            f"📥 **Downloading Video Assets...**\n"
                            f"🎛️ *Status:* `Syncing independent trending audio track`\n\n"
                            f"🎬 **Progress:** `{bar}`\n"  
                            f"⚡ **Speed:** `{speed_str}`"  
                        ),  
                        loop  
                    )
                except Exception:  
                    pass

async def pyrogram_upload_callback(current, total, status_msg):
    global last_edit_time
    now = time.time()

    if now - last_edit_time > 2.0:  
        last_edit_time = now  
        percentage = int((current / total) * 100)  
        bar = create_progress_bar(percentage)  
          
        current_mb = current / (1024 * 1024)  
        total_mb = total / (1024 * 1024)  
          
        try:  
            await status_msg.edit(  
                f"📤 **Uploading Force-Merged Video to Telegram...**\n\n"  
                f"🚀 **Progress:** `{bar}`\n"  
                f"📦 **Size:** `{current_mb:.2f} MB` / `{total_mb:.2f} MB`"  
            )  
        except Exception:  
            pass

def fetch_instagram_data_and_comments(url):
    clean_url = url.split("?")[0].strip().rstrip("/")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'get_comments': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        }
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            video_url = info.get('url') or (info['formats'][-1]['url'] if 'formats' in info else None)
            caption_text = info.get('description') or info.get('title') or 'No Caption'
            
            audio_url = None
            if not info.get('requested_formats') or not any(f.get('vcodec') == 'none' for f in info.get('requested_formats', [])):
                audio_url = info.get('audio_url') or info.get('music_url')

            comments_list = []
            raw_comments = info.get('comments', [])
            if raw_comments:
                sorted_comments = sorted(raw_comments, key=lambda x: (x.get('like_count', 0) or 0), reverse=True)
                for c in sorted_comments[:10]:
                    author = c.get('author', 'anonymous_user')
                    text = c.get('text', '').strip().replace('\n', ' ')
                    if text: comments_list.append(f"💬 @{author}: {text}")

            if video_url:
                return {
                    "success": True,
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "title": caption_text.strip(),
                    "uploader": info.get('uploader', 'Instagram_Creator'),
                    "id": info.get('id') or str(int(time.time())),
                    "comments": comments_list
                }
    except Exception:
        pass
        
    # Fallback API if yt-dlp fails
    try:
        api_url = f"https://api.vkrsu.my.id/social/download?url={clean_url}"
        res = requests.get(api_url, timeout=10).json()
        data = res.get("data", res.get("result", {}))
        if isinstance(data, list) and len(data) > 0: data = data[0]
        v_url = data.get("url") or data.get("video")
        if v_url:
            return {
                "success": True,
                "video_url": v_url,
                "audio_url": data.get("audio") or data.get("audio_url"),
                "title": data.get("caption", "No Caption"),
                "uploader": data.get("username", "Instagram_User"),
                "id": str(int(time.time())),
                "comments": []
            }
    except Exception:
        pass
        
    return {"success": False}

def download_and_mux_streams(url, data, vid_id):
    out_file = f"video_{vid_id}.mp4"
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_file,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'progress_hooks': [yt_dlp_callback],
    }
        
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    if data.get("audio_url") and os.path.exists(out_file):
        temp_audio = f"audio_{vid_id}.m4a"
        try:
            r = requests.get(data["audio_url"], timeout=30)
            with open(temp_audio, 'wb') as f:
                f.write(r.content)
            
            muxed_file = f"muxed_{vid_id}.mp4"
            os.system(f"ffmpeg -y -i {out_file} -i {temp_audio} -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 {muxed_file} >/dev/null 2>&1")
            
            if os.path.exists(muxed_file) and os.path.getsize(muxed_file) > 1000:
                os.remove(out_file)
                os.remove(temp_audio)
                return muxed_file
            if os.path.exists(temp_audio): os.remove(temp_audio)
        except Exception:
            if os.path.exists(temp_audio): os.remove(temp_audio)
            
    return out_file

# --- HANDLERS & PLUGINS ---

@app.on_message(filters.text & filters.regex(INSTAGRAM_REGEX) & ~app.bl_users)
async def auto_detect_instagram_link(client, message):
    global current_status_msg, last_edit_time
    
    match = re.search(r'(https?://[^\s]+)', message.text)  
    if not match: return  
          
    url = match.group(1)
    status_msg = await message.reply_text("⚡ **Link detected!** Extracting trending audio layout + comments graph...")  
    
    loop_engine = asyncio.get_running_loop()  
    current_status_msg = status_msg  
    last_edit_time = 0  

    data = await loop_engine.run_in_executor(None, fetch_instagram_data_and_comments, url)  
    
    if not data.get("success") or not data.get("video_url"):
        await status_msg.edit("❌ **Extraction Failed!** Link restricted or account cookies are invalid.")
        return

    caption = (  
        f"⚡ **Instagram Reel Downloaded** ⚡\n\n"  
        f"👤 **Uploader :** @{data.get('uploader')}\n"  
        f"🎵 **Audio Track :** `Synced / Muxed (Trending Fixed)`\n\n"  
        f"📝 **Caption :** {data.get('title')[:180]}...\n"  
    )  
    
    if data.get("comments"):
        caption += "\n📊 **Top 10 User Comments:**\n" + "\n".join(data["comments"])
    else:
        caption += "\n📊 **Top 10 User Comments:**\n💬 No public comments indexed or session restricted."

    if len(caption) > 1010: caption = caption[:970] + "\n\n...[Truncated]"

    try:  
        await status_msg.edit("📥 **Downloading stream modules... Merging external audio asset files...**")
        file_path = await loop_engine.run_in_executor(None, download_and_mux_streams, url, data, data["id"])

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:  
            await status_msg.edit("📤 **Audio and Video multiplexed successfully! Uploading...**")  
              
            await message.reply_video(  
                video=file_path,   
                caption=caption,  
                progress=pyrogram_upload_callback,  
                progress_args=(status_msg,)  
            )  
              
            await status_msg.delete()  
            os.remove(file_path)  
        else:
            await status_msg.edit("❌ **Extraction Failed!** Output stream broke down.")
            if os.path.exists(file_path): os.remove(file_path)
              
    except Exception as e:  
        await status_msg.edit(f"❌ Pipeline broke down during workflow.\nError: {e}")
        if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)

__MODULE__ = "Iɴsᴛᴀɢʀᴀᴍ"
__HELP__ = """
ℹ️ **Instagram Auto Downloader**:
Paste any Instagram link (reel, post, tv), and the bot will multiplex split external trending audios and extract top 10 liked comments automatically!
"""
