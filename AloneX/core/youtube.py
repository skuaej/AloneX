import os
import re
import random
import asyncio
import aiohttp
import yt_dlp
from py_yt import VideosSearch, Playlist
from AloneX import app, logger, config
from AloneX.helpers import Track, utils
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.errors import FloodWait

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
        
        # Initialize Database Index Collection Natively
        self.cache_col = None
        if hasattr(config, "MONGO_URL") and config.MONGO_URL:
            try:
                self.mongo_client = AsyncIOMotorClient(config.MONGO_URL)
                self.db = self.mongo_client["AloneX_Cloud_Cache"]
                self.cache_col = self.db["tracks"]
                
                # Automatically create text search indexes for plain-text matches
                asyncio.ensure_future(self.cache_col.create_index([("title", "text")]))
            except Exception as e:
                logger.error(f"Failed to initialize MongoDB Cache Indexer: {e}")

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
        # LAYER 0: Local MongoDB Database text match lookup
        if self.cache_col is not None:
            try:
                db_match = await self.cache_col.find_one({"$text": {"$search": query}})
                if db_match:
                    logger.info(f"Database text-index cache hit for query: '{query}'")
                    return Track(
                        id=db_match.get("video_id"),
                        channel_name="Database Cache",
                        duration="03:00", # Fixed duration string to prevent 0-minute live stream bug
                        duration_sec=180, # Fixed duration integer so the queue processor moves smoothly
                        message_id=m_id,
                        title=db_match.get("title", "Cached Audio")[:25],
                        thumbnail=getattr(config, "DEFAULT_THUMB", "https://telegra.ph/file/default.jpg"),
                        url=f"https://youtube.com/watch?v={db_match.get('video_id')}",
                        view_count="N/A",
                        video=db_match.get("video", False),
                    )
            except Exception as e:
                logger.error(f"Database pre-search lookup error: {e}")

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

    async def download(self, video_id: str, video: bool = False, title: str = "Unknown Track") -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        cache_channel = getattr(config, "CACHE_CHANNEL", None)
        
        # -----------------------------------------------------------------
        # LAYER 1: Check Local Storage Cache first
        # -----------------------------------------------------------------
        cached_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(f"{video_id}.")]
        if cached_files:
            for file_name in cached_files:
                file_path = os.path.join(DOWNLOAD_DIR, file_name)
                if video and file_path.endswith((".mp4", ".mkv", ".webm")):
                    return file_path
                elif not video and file_path.endswith((".webm", ".m4a", ".mp3")):
                    return file_path
            return os.path.join(DOWNLOAD_DIR, cached_files[0])

        # -----------------------------------------------------------------
        # LAYER 2: Cloud Channel DB Extraction (Anti-Ban Architecture)
        # -----------------------------------------------------------------
        if cache_channel:
            msg = None
            
            # Step A: Check MongoDB first (0% Telegram overhead)
            if self.cache_col is not None:
                try:
                    cache_data = await self.cache_col.find_one({"video_id": video_id})
                    if cache_data:
                        msg_id = cache_data.get("message_id")
                        logger.info(f"MongoDB hit for ID {video_id}. Main Bot fetching message directly...")
                        msg = await app.get_messages(chat_id=cache_channel, message_ids=msg_id)
                        if msg and msg.empty:
                            msg = None
                except Exception as db_err:
                    logger.error(f"MongoDB collection query error: {db_err}")
            
            # Step B: Read-Only Userbot Search Fallback Rotation (Budget Setup Safety)
            if not msg:
                from AloneX import userbot
                available_clients = []
                
                # Check for Assistant 1 dynamically. If 2 & 3 don't exist, it safely skips them.
                if hasattr(userbot, "one") and userbot.one and getattr(userbot.one, "is_connected", False): 
                    available_clients.append(("Assistant 1", userbot.one))
                if hasattr(userbot, "two") and userbot.two and getattr(userbot.two, "is_connected", False): 
                    available_clients.append(("Assistant 2", userbot.two))
                if hasattr(userbot, "three") and userbot.three and getattr(userbot.three, "is_connected", False): 
                    available_clients.append(("Assistant 3", userbot.three))
                
                for client_name, client in available_clients:
                    try:
                        # Userbots ONLY perform text search lookups to extract a message ID
                        async for m in client.search_messages(chat_id=cache_channel, query=video_id, limit=1):
                            if m.video or m.audio or m.document:
                                # We hand the ID to the main Bot token to bypass userbot flood limits
                                msg = await app.get_messages(chat_id=cache_channel, message_ids=m.id)
                                break
                        break  
                    except FloodWait as fw:
                        logger.warning(f"{client_name} caught in flood wait. Rotating or cooling down...")
                        await asyncio.sleep(1)
                        continue
                    except Exception as ub_err:
                        logger.error(f"{client_name} text query error: {ub_err}")
                        continue

            # Step C: Downstream Media Extraction (Executed ONLY by Bot Token)
            if msg and (msg.video or msg.audio or msg.document):
                try:
                    media = msg.video or msg.audio or msg.document
                    ext = "mp4" if msg.video else ("m4a" if msg.audio else "webm")
                    if media.file_name and "." in media.file_name:
                        ext = media.file_name.split(".")[-1]
                        
                    local_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
                    
                    # Main Bot runs the download, using block=True to prevent voice chat frame skipping
                    await app.download_media(message=msg, file_name=local_path, block=True)
                    
                    if os.path.exists(local_path):
                        if self.cache_col is not None:
                            await self.cache_col.update_one(
                                {"video_id": video_id},
                                {"$set": {"message_id": msg.id, "title": title.lower(), "video": bool(msg.video)}},
                                upsert=True
                            )
                        return local_path
                except Exception as process_err:
                    logger.error(f"Main Bot failed executing media file stream: {process_err}")

        # -----------------------------------------------------------------
        # LAYER 3: Core YouTube DL Pipeline (Only if nowhere else found)
        # -----------------------------------------------------------------
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookie_file = self.get_cookies()

        ydl_opts = {
            'format': 'bestvideo[height<=240]+bestaudio/best' if video else 'bestaudio/best',
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
                return ydl.prepare_filename(info), info.get("title", "Unknown Track")

        try:
            loop = asyncio.get_event_loop()
            downloaded_file, extracted_title = await loop.run_in_executor(None, extract)
            final_title = extracted_title if title == "Unknown Track" else title
            
            if os.path.exists(downloaded_file):
                if cache_channel:
                    try:
                        cloud_caption = f"Saves:\n{video_id}\n\n{video_id}\nTitle: {final_title}"
                        
                        # Main Bot performs the backup upload task
                        if video:
                            saved_msg = await app.send_video(chat_id=cache_channel, video=downloaded_file, caption=cloud_caption)
                        else:
                            saved_msg = await app.send_audio(chat_id=cache_channel, audio=downloaded_file, caption=cloud_caption)
                        
                        if saved_msg and self.cache_col is not None:
                            await self.cache_col.update_one(
                                {"video_id": video_id},
                                {"$set": {"message_id": saved_msg.id, "title": final_title.lower(), "video": video}},
                                upsert=True
                            )
                    except Exception as upload_err:
                        logger.error(f"Failed copying file into backup storage channel: {upload_err}")
                        
                return downloaded_file

        except Exception as e:
            logger.error(f"yt-dlp core pipeline execution exception: {e}")
            
        return None
        
