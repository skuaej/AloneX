import os
import re
import asyncio
import aiohttp
import urllib.parse
from py_yt import VideosSearch, Playlist
from AloneX import logger, config
from AloneX.helpers import Track, utils

# Eldian API Setup
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

    # ELDIAN API: 1-SECOND INSTANT DOWNLOADER
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "m4a"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # Instant skip if we already downloaded it before
        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            return file_path

        try:
            # 1. URL ENCODE to match your API JSON exactly (https%3A%2F%2F...)
            # This stops the API from spending time redirecting or parsing raw symbols
            yt_url = urllib.parse.quote(f"https://www.youtube.com/watch?v={video_id}")
            
            # 2. Use the exact stream route (140 kbps audio = fast ~4MB file)
            if video:
                target_url = f"{API_URL}/api/stream_video?url={yt_url}&quality=338p"
            else:
                target_url = f"{API_URL}/api/stream_audio?url={yt_url}&format_id=140"

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
            
            # 3. INSTANT DOWNLOAD: Grab the whole file at once instead of looping chunks
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(target_url, allow_redirects=True) as dl_resp:
                    if dl_resp.status == 200:
                        # `.read()` pulls the entire audio into memory instantly. 
                        # This avoids the slow I/O overhead of writing small chunks.
                        file_data = await dl_resp.read()
                        with open(file_path, "wb") as f:
                            f.write(file_data)
                    else:
                        logger.error(f"API Error {dl_resp.status} for {video_id}")
                        return None

            # Verify and return
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                return file_path
            else:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None

        except Exception as e:
            logger.error(f"1-Second Download error for {video_id}: {e}")
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            return None
