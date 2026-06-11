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
        
        self.cache_col = None
        if hasattr(config, "MONGO_URL") and config.MONGO_URL:
            try:
                self.mongo_client = AsyncIOMotorClient(config.MONGO_URL)
                self.db = self.mongo_client["AloneX_Cloud_Cache"]
                self.cache_col = self.db["tracks"]
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
        try:
            is_url = self.valid(query)

            if is_url:
                match = re.match(self.regex, query)
                if match and match.group(5):
                    extracted_id = match.group(5)
                    if not extracted_id.startswith("PL"):
                        query = extracted_id
            else:
                # ---------------------------------------------------------
                # LAYER 0: Strict Database Pre-Search (PRIORITIZES CACHE!)
                # ---------------------------------------------------------
                if self.cache_col is not None:
                    try:
                        # Regex safely matches exact phrases (e.g., "jo dil ke pass" matches "jo dil ke pass rahte hain")
                        safe_query = re.escape(query.strip())
                        db_match = await self.cache_col.find_one(
                            {"title": {"$regex": safe_query, "$options": "i"}, "video": video}
                        )
                        if db_match:
                            logger.info(f"⚡ DB Title Match Hit! '{query}' -> '{db_match.get('title')}'")
                            return Track(
                                id=db_match.get("video_id"),
                                channel_name="Database Cache",
                                duration="04:00", 
                                duration_sec=240, 
                                message_id=m_id,
                                title=db_match.get("title", "Cached Track")[:25],
                                thumbnail=getattr(config, "DEFAULT_THUMB", "https://telegra.ph/file/default.jpg"),
                                url=f"https://youtube.com/watch?v={db_match.get('video_id')}",
                                view_count="Cached",
                                video=db_match.get("video", False),
                            )
                    except Exception as db_err:
                        logger.error(f"DB Regex Search error: {db_err}")

            # Fallback to YouTube if not found in Database
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
        
        cache_channel = getattr(config, "VIDEO_CACHE_CHANNEL", None) if video else getattr(config, "AUDIO_CACHE_CHANNEL", None)
        file_prefix = f"{video_id}_video" if video else f"{video_id}_audio"

        # -----------------------------------------------------------------
        # LAYER 1: Check Local Storage Cache first 
        # -----------------------------------------------------------------
        cached_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(f"{file_prefix}.")]
        if cached_files:
            logger.info(f"⚡ Local Cache hit! Instantly loading: {cached_files[0]}")
            return os.path.join(DOWNLOAD_DIR, cached_files[0])

        # -----------------------------------------------------------------
        # LAYER 2: Cloud Channel DB Extraction
        # -----------------------------------------------------------------
        if cache_channel:
            msg = None
            
            if self.cache_col is not None:
                try:
                    cache_data = await self.cache_col.find_one({"video_id": video_id, "video": video})
                    if cache_data:
                        msg_id = cache_data.get("message_id")
                        logger.info(f"MongoDB hit for ID {video_id}. Fetching from channel: {cache_channel}...")
                        msg = await app.get_messages(chat_id=cache_channel, message_ids=msg_id)
                        if msg and msg.empty:
                            msg = None
                except Exception as db_err:
                    logger.error(f"MongoDB collection query error: {db_err}")
            
            if not msg:
                from AloneX import userbot
                available_clients = []
                
                if hasattr(userbot, "one") and userbot.one and getattr(userbot.one, "is_connected", False): 
                    available_clients.append(("Assistant 1", userbot.one))
                if hasattr(userbot, "two") and userbot.two and getattr(userbot.two, "is_connected", False): 
                    available_clients.append(("Assistant 2", userbot.two))
                if hasattr(userbot, "three") and userbot.three and getattr(userbot.three, "is_connected", False): 
                    available_clients.append(("Assistant 3", userbot.three))
                
                for client_name, client in available_clients:
                    try:
                        async for m in client.search_messages(chat_id=cache_channel, query=video_id, limit=3):
                            if video and m.video:
                                msg = await app.get_messages(chat_id=cache_channel, message_ids=m.id)
                                break
                            elif not video and (m.audio or m.document or m.voice):
                                msg = await app.get_messages(chat_id=cache_channel, message_ids=m.id)
                                break
                        if msg:
                            break  
                    except FloodWait as fw:
                        logger.warning(f"{client_name} caught in flood wait. Rotating...")
                        await asyncio.sleep(1)
                        continue
                    except Exception as ub_err:
                        logger.error(f"{client_name} search query error: {ub_err}")
                        continue

            if msg and (msg.video or msg.audio or msg.document or msg.voice):
                try:
                    media = msg.video or msg.audio or msg.document or msg.voice
                    ext = "mp4" if msg.video else ("m4a" if msg.audio else "webm")
                    if hasattr(media, "file_name") and media.file_name and "." in media.file_name:
                        ext = media.file_name.split(".")[-1]
                        
                    local_path = os.path.join(DOWNLOAD_DIR, f"{file_prefix}.{ext}")
                    await app.download_media(message=msg, file_name=local_path, block=True)
                    
                    if os.path.exists(local_path):
                        if self.cache_col is not None:
                            await self.cache_col.update_one(
                                {"video_id": video_id, "video": video},
                                {"$set": {"message_id": msg.id, "title": title.lower(), "video": bool(msg.video)}},
                                upsert=True
                            )
                        return local_path
                except Exception as process_err:
                    logger.error(f"Main Bot failed executing media file stream: {process_err}")

        # -----------------------------------------------------------------
        # LAYER 3: Core YouTube DL Pipeline (Stable Version)
        # -----------------------------------------------------------------
        url = f"https://www.youtube.com/watch?v={video_id}"
        cookie_file = self.get_cookies()

        ydl_opts = {
            'format': 'bestvideo[height<=240]+bestaudio/best' if video else 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, f"{file_prefix}.%(ext)s"),
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
                        format_str = "Video" if video else "Audio"
                        cloud_caption = f"Saves: {format_str}\n{video_id}\n\nTitle: {final_title}"
                        
                        if video:
                            saved_msg = await app.send_video(chat_id=cache_channel, video=downloaded_file, caption=cloud_caption)
                        else:
                            saved_msg = await app.send_audio(chat_id=cache_channel, audio=downloaded_file, caption=cloud_caption)
                        
                        if saved_msg and self.cache_col is not None:
                            await self.cache_col.update_one(
                                {"video_id": video_id, "video": video},
                                {"$set": {"message_id": saved_msg.id, "title": final_title.lower(), "video": video}},
                                upsert=True
                            )
                    except Exception as upload_err:
                        logger.error(f"Failed copying file into backup storage channel: {upload_err}")
                        
                return downloaded_file

        except Exception as e:
            logger.error(f"yt-dlp core pipeline execution exception: {e}")
            
        return None
        
