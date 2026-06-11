
import os
import re
import random
import asyncio
import aiohttp
import yt_dlp
from py_yt import VideosSearch, Playlist
from AloneX import app, logger, config
from AloneX.helpers import Track, utils

DOWNLOAD_DIR = "downloads"

class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.cookie_dir = "AloneX/cookies"

    def get_cookies(self):
        if not os.path.exists(self.cookie_dir):
            return None
        cookies_files = [f for f in os.listdir(self.cookie_dir) if f.endswith(".txt")]
        if not cookies_files:
            return None
        return os.path.join(self.cookie_dir, random.choice(cookies_files))

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        if not os.path.exists(self.cookie_dir):
            os.makedirs(self.cookie_dir)
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(urls):
                path = f"{self.cookie_dir}/cookie_{i}.txt"
                link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
            if results and results["result"]:
                data = results["result"][0]
                return Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name"),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")) if data.get("duration") else 0,
                    message_id=m_id,
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    video=video,
                )
        except Exception as e:
            logger.error(f"Search error: {e}")
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist.get("videos", [])[:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")) if data.get("duration") else 0,
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception as e:
            logger.error(f"Playlist error: {e}")
        return tracks

    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        cache_channel = getattr(config, "CACHE_CHANNEL", None)
        
        # LAYER 1: Check Local Storage Cache first
        cached_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(f"{video_id}.")]
        if cached_files:
            for file_name in cached_files:
                file_path = os.path.join(DOWNLOAD_DIR, file_name)
                if video and file_path.endswith((".mp4", ".mkv", ".webm")):
                    logger.info(f"Local Cache Match (Video): {file_path}")
                    return file_path
                elif not video and file_path.endswith((".webm", ".m4a", ".mp3")):
                    logger.info(f"Local Cache Match (Audio): {file_path}")
                    return file_path
            return os.path.join(DOWNLOAD_DIR, cached_files[0])

        # LAYER 2: Search and Fetch from Telegram Channel
        if cache_channel:
            try:
                logger.info(f"Searching cloud cache channel for ID: {video_id}")
                async for msg in app.search_messages(chat_id=cache_channel, query=video_id, limit=3):
                    if msg.video or msg.audio or msg.document:
                        media = msg.video or msg.audio or msg.document
                        
                        ext = "mp4" if msg.video else ("m4a" if msg.audio else "webm")
                        if media.file_name and "." in media.file_name:
                            ext = media.file_name.split(".")[-1]
                            
                        local_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
                        logger.info(f"Cloud Cache Found! Fetching from Telegram: {local_path}")
                        
                        await app.download_media(message=msg, file_name=local_path)
                        if os.path.exists(local_path):
                            return local_path
            except Exception as e:
                logger.error(f"Failed to query Telegram cloud storage index: {e}")

        # LAYER 3: Extract via YouTube DL Pipeline
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookie_file = self.get_cookies()

        ydl_opts = {
            'format': 'bestvideo[height<=720]+bestaudio/best' if video else 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s"),
            'geo_bypass': True,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
        }

        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file

        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        try:
            loop = asyncio.get_event_loop()
            downloaded_file = await loop.run_in_executor(None, extract)
            
            if os.path.exists(downloaded_file):
                logger.info(f"Download complete via YouTube core: {downloaded_file}")
                
                # LAYER 4: Back up to Telegram Cloud Storage
                if cache_channel:
                    try:
                        logger.info(f"Backing up file to cloud index channel...")
                        if video:
                            await app.send_video(chat_id=cache_channel, video=downloaded_file, caption=f"{video_id}")
                        else:
                            await app.send_audio(chat_id=cache_channel, audio=downloaded_file, caption=f"{video_id}")
                    except Exception as upload_err:
                        logger.error(f"Failed to copy file into database cache channel: {upload_err}")
                        
                return downloaded_file

        except Exception as e:
            logger.error(f"yt-dlp execution exception for video asset {video_id}: {e}")
            
        return None
