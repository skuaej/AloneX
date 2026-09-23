import os
import re
import aiohttp
from py_yt import VideosSearch, Playlist
from AloneX import logger, config
from AloneX.helpers import Track, utils

# Eldian Music API
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

    def _extract_id(self, video_id: str) -> str | None:
        """Extract clean 11-char video ID from URL or raw ID"""
        if not video_id:
            return None
        if len(video_id) == 11 and re.match(r"^[A-Za-z0-9_-]{11}$", video_id):
            return video_id
        match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", video_id)
        return match.group(1) if match else None

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
        video_id = self._extract_id(video_id)
        if not video_id:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "m4a"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # Return cached file if exists
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            return file_path

        try:
            async with aiohttp.ClientSession() as session:
                if video:
                    url = f"{API_URL}/mp4"
                    params = {"video_id": video_id, "resolution": "720"}
                    timeout_sec = 600
                else:
                    url = f"{API_URL}/audio"
                    params = {"video_id": video_id, "quality": "192"}
                    timeout_sec = 300

                timeout = aiohttp.ClientTimeout(total=timeout_sec)

                async with session.get(
                    url,
                    params=params,
                    timeout=timeout,
                    allow_redirects=True
                ) as resp:

                    if resp.status != 200:
                        logger.error(f"[Eldian] Download failed: {resp.status} for {video_id}")
                        return None

                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
                return file_path

        except Exception as e:
            logger.error(f"Eldian download exception ({video_id}): {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

        return None
