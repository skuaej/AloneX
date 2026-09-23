import os
import re
import asyncio
import aiohttp
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

    # ELDIAN API: INSTANT STREAMING WITH WARM-UP PING
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "mp3"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # 1. Check if we already have it downloaded from earlier
        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            logger.info(f"Using locally cached file for {video_id}")
            return file_path

        try:
            logger.info(f"Warming up API stream for {video_id} (Preventing Voice Chat Timeout)...")
            
            # 2. WARM-UP PING: Force the API to process the video first
            # This prevents PyTgCalls from crashing while the API is "thinking"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{API_URL}/api/info",
                    json={"input": f"https://youtu.be/{video_id}"},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Eldian API could not process {video_id} (Status: {resp.status})")
                        return None
                        
            # 3. Now that the API has prepared the song, generate the direct stream link
            if video:
                stream_url = f"{API_URL}/mp4?video_id={video_id}&resolution=360"
            else:
                stream_url = f"{API_URL}/audio?video_id={video_id}&quality=128"

            logger.info(f"Stream ready! Passing {video_id} directly to PyTgCalls.")
            return stream_url

        except asyncio.TimeoutError:
            logger.error(f"API Warm-up timed out for {video_id}. The API server is busy.")
            return None
        except Exception as e:
            logger.error(f"Failed to generate stream link for {video_id}: {e}")
            return None
