import os
import re
import aiohttp
from py_yt import VideosSearch, Playlist
from AloneX import logger, config
from AloneX.helpers import Track, utils

# ShrutiBots API Setup
API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsqZ0l3c4nmL8JdWEPVQRG")
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

    # ShrutiBots API Integrated Download Function
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        # Using mp4 for video, mp3 for audio
        ext = "mp4" if video else "mp3" 
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # Return existing file if it's already downloaded
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path

        try:
            async with aiohttp.ClientSession() as session:
                dl_type = "video" if video else "audio"
                timeout_limit = 600 if video else 300
                
                async with session.get(
                    f"{API_URL}/download",
                    params={"url": video_id, "type": dl_type, "api_key": API_KEY},
                    timeout=aiohttp.ClientTimeout(total=timeout_limit)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"[Shruti API] Download failed with status: {resp.status}")
                        return None
                    
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                return file_path
                
        except Exception as e:
            logger.error(f"Shruti API Download exception for ID {video_id}: {e}")
            if os.path.exists(file_path):
                try: 
                    os.remove(file_path)
                except: 
                    pass
                    
        return None
        
