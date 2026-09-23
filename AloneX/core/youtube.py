import os
import re
import asyncio
import aiohttp
from py_yt import VideosSearch, Playlist
from AloneX import logger, config
from AloneX.helpers import Track, utils

# Eldian API Setup (No Key Required)
API_URL = os.environ.get("ELDIAN_API_URL", "https://eldian-music-api-production.up.railway.app")
DOWNLOAD_DIR = "downloads"

class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )

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

    # Eldian API Integrated Download Function (Anti-Hang & Redirects Enabled)
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "mp3" 
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # Ensure file isn't empty/corrupted before returning
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            logger.info(f"File already exists in cache: {file_path}")
            return file_path

        try:
            async with aiohttp.ClientSession() as session:
                if video:
                    endpoint = f"{API_URL}/mp4"
                    params = {"video_id": video_id, "resolution": "720"}
                else:
                    endpoint = f"{API_URL}/audio"
                    params = {"video_id": video_id, "quality": "320"}
                
                # Fake User-Agent so the server/cloudflare doesn't block the bot
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                }

                timeout_limit = 600 if video else 300
                logger.info(f"Downloading {video_id} via Eldian API... (Following redirects)")
                
                async with session.get(
                    endpoint,
                    params=params,
                    headers=headers,
                    allow_redirects=True, # THIS IS THE CRITICAL FIX for Google CDN
                    timeout=aiohttp.ClientTimeout(total=timeout_limit)
                ) as resp:
                    
                    if resp.status not in (200, 206): # CDN might return 206 Partial Content
                        error_text = await resp.text()
                        logger.error(f"API Download failed (Status: {resp.status}). Response: {error_text}")
                        return None
                    
                    with open(file_path, "wb") as f:
                        # Writing in slightly smaller chunks for better stability
                        async for chunk in resp.content.iter_chunked(65536): 
                            f.write(chunk)

            # Final check to confirm it actually finished successfully
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                if file_size > 1024:
                    logger.info(f"Successfully downloaded {video_id}! Size: {file_size // 1024} KB")
                    return file_path
                else:
                    logger.error(f"Downloaded file is empty or corrupted (Size: {file_size} bytes)")
                    os.remove(file_path)
                    return None
            else:
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"Download timed out for {video_id}! The API took too long to respond.")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None
        except Exception as e:
            logger.error(f"Download exception for ID {video_id}: {e}")
            if os.path.exists(file_path):
                try: 
                    os.remove(file_path)
                except: 
                    pass
                    
        return None

