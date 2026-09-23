
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

    # ELDIAN API: FREEZE-PROOF DOWNLOADER
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "mp3"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # 1. Use cached file if it exists to save time
        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            logger.info(f"Using locally cached file for {video_id}")
            return file_path

        # Delete any broken 0-byte file from previous hangs
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

        try:
            logger.info(f"Downloading {video_id} using Eldian API Standard Links...")
            
            # 2. Construct the exact URL you requested
            if video:
                target_url = f"{API_URL}/mp4?video_id={video_id}&resolution=480"
            else:
                target_url = f"{API_URL}/audio?video_id={video_id}&quality=192"

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            
            # CRITICAL FIX: sock_read=10 prevents the bot from hanging if Google CDN IP-blocks the connection!
            client_timeout = aiohttp.ClientTimeout(total=180, connect=15, sock_read=10)

            async with aiohttp.ClientSession(headers=headers, timeout=client_timeout) as session:
                
                # 3. Download the file safely, following redirects
                async with session.get(target_url, allow_redirects=True) as dl_resp:
                    if dl_resp.status not in (200, 206):
                        logger.error(f"API returned status {dl_resp.status} for URL {target_url}")
                        return None
                        
                    with open(file_path, "wb") as f:
                        # CRITICAL FIX: 64KB chunks. 1MB was too large and caused freezing on throttled CDN links.
                        async for chunk in dl_resp.content.iter_chunked(65536): 
                            f.write(chunk)

            # 4. Verify successful download
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                logger.info(f"Successfully downloaded {video_id}! Ready to play.")
                return file_path
            else:
                logger.error(f"Downloaded file for {video_id} is empty or corrupted.")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None

        except asyncio.TimeoutError:
            # If Google blocks the CDN redirect, it throws this error instead of hanging your whole bot!
            logger.error(f"Download timed out for {video_id}! Google CDN likely blocked the API redirect.")
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
