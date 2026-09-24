
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

    # ELDIAN API: ULTRA-FAST DIRECT DOWNLOAD (1-2 SECONDS)
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "m4a"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # Instant return if file already exists
        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            return file_path

        # Clear out broken empty files
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

        try:
            # DIRECT ROUTING: Skip JSON fetch entirely and use the exact proxy routes
            if video:
                target_url = f"{API_URL}/api/stream_video?url=https://www.youtube.com/watch?v={video_id}&quality=338p"
            else:
                # format_id=140 is the lightweight m4a audio stream
                target_url = f"{API_URL}/api/stream_audio?url=https://www.youtube.com/watch?v={video_id}&format_id=140"

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
            
            # Use 1MB chunks to blast the data to the hard drive instantly
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(target_url, allow_redirects=True) as dl_resp:
                    if dl_resp.status not in (200, 206):
                        return None
                        
                    with open(file_path, "wb") as f:
                        async for chunk in dl_resp.content.iter_chunked(1048576): 
                            f.write(chunk)

            # Verification
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                return file_path
            else:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None

        except Exception as e:
            logger.error(f"Fast Download error for {video_id}: {e}")
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            return None
