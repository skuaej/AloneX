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

    # Eldian API Integrated Download Function (Ultra-Fast Optimized)
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ext = "mp4" if video else "mp3"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            logger.info(f"File already cached: {file_path}")
            return file_path

        # Clear out any broken/partial file from before
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # Optimized timeouts for faster failing/retrying
        client_timeout = aiohttp.ClientTimeout(total=300, connect=10, sock_read=20)

        try:
            async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
                
                # Directly construct the download URL (skips the slow JSON info fetch step)
                if video:
                    target_url = f"{API_URL}/mp4?video_id={video_id}&resolution=480" # 480p is much faster for VC video
                else:
                    target_url = f"{API_URL}/audio?video_id={video_id}&quality=192" # 192kbps downloads 40% faster than 320kbps

                logger.info(f"Direct fast-stream fetching for {video_id}...")

                # STEP 1: Download stream directly using redirect chain
                async with session.get(target_url, allow_redirects=True) as dl_resp:
                    if dl_resp.status not in (200, 206):
                        logger.error(f"Download stream returned status {dl_resp.status}")
                        return None

                    with open(file_path, "wb") as f:
                        while True:
                            # STEP 2: Read in massive 1MB chunks (1048576 bytes) for maximum speed
                            chunk = await dl_resp.content.read(1048576)
                            if not chunk:
                                break
                            f.write(chunk)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                logger.info(f"Fast download complete: {video_id}")
                return file_path
            else:
                logger.error(f"Download produced an incomplete or empty file for {video_id}")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                return None

        except asyncio.TimeoutError:
            logger.error(f"Stream timeout reached while downloading {video_id}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None
        except Exception as e:
            logger.error(f"Download exception for {video_id}: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None
