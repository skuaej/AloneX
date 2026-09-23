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

    # ELDIAN API: ULTRA-FAST LOCAL DOWNLOADER
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "mp3"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # 1. Use cached file if it exists
        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            logger.info(f"Using locally cached file for {video_id}")
            return file_path

        try:
            logger.info(f"Fast-downloading {video_id} to local server...")
            
            target_url = None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

            async with aiohttp.ClientSession(headers=headers) as session:
                # 2. Ping API for the freshest download link (Prevents CDN stalling)
                async with session.post(
                    f"{API_URL}/api/info",
                    json={"input": f"https://youtu.be/{video_id}"},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as info_resp:
                    if info_resp.status == 200:
                        data = await info_resp.json()
                        # Grab the lowest quality to ensure fastest possible download
                        if video and data.get("mp4_formats"):
                            target_url = data["mp4_formats"][0].get("download_url") # Usually 144p or 240p
                        elif not video and data.get("audio_formats"):
                            target_url = data["audio_formats"][0].get("download_url") # 128kbps

                # Fallback if the info route fails
                if not target_url:
                    if video:
                        target_url = f"{API_URL}/mp4?video_id={video_id}&resolution=360"
                    else:
                        target_url = f"{API_URL}/audio?video_id={video_id}&quality=128"

                # 3. Download the file in massive chunks
                async with session.get(target_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=120)) as dl_resp:
                    if dl_resp.status not in (200, 206):
                        logger.error(f"API returned status {dl_resp.status}")
                        return None
                        
                    with open(file_path, "wb") as f:
                        async for chunk in dl_resp.content.iter_chunked(1048576): # 1 MB chunks for speed
                            f.write(chunk)

            # 4. Verify successful download
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                logger.info(f"Successfully downloaded {video_id}! Ready to play.")
                return file_path
            else:
                logger.error(f"Downloaded file for {video_id} is corrupted.")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None

        except asyncio.TimeoutError:
            logger.error(f"Download timed out for {video_id}. API is overloaded.")
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            return None
        except Exception as e:
            logger.error(f"Download error for {video_id}: {e}")
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            return None

