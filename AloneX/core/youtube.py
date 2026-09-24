import os
import re
import asyncio
import aiohttp
from py_yt import VideosSearch, Playlist
from AloneX import logger, config
from AloneX.helpers import Track, utils

# Updated Eldian API Setup
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

    # UPDATED API ROUTING: LOCAL DOWNLOADER
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        # We use m4a for audio to match the new API format 140
        ext = "mp4" if video else "m4a"
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

        # 1. Use cached file to skip downloading if already played
        if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
            logger.info(f"Using locally cached file for {video_id}")
            return file_path

        # Clear out broken empty files
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

        try:
            logger.info(f"Fetching new API routes for {video_id}...")
            target_url = None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
            
            async with aiohttp.ClientSession(headers=headers) as session:
                
                # 2. Ping the base route to get the JSON output
                # Adjust this if your JSON route is different (e.g. /api/info)
                async with session.get(
                    f"{API_URL}/api/info?url=https://www.youtube.com/watch?v={video_id}",
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as info_resp:
                    
                    if info_resp.status == 200:
                        data = await info_resp.json()
                        
                        if video and data.get("video_streams_with_sound"):
                            # Find a ~360p or 338p stream for fast video playback
                            for stream in data["video_streams_with_sound"]:
                                if stream.get("quality") == "338p":
                                    target_url = stream.get("download_url")
                                    break
                            if not target_url:
                                target_url = data["video_streams_with_sound"][-1].get("download_url")
                                
                        elif not video and data.get("audio_streams"):
                            # Look for format_id 140 (m4a) which PyTgCalls loves
                            for stream in data["audio_streams"]:
                                if stream.get("format_id") == "140":
                                    target_url = stream.get("stream_url")
                                    break
                            if not target_url:
                                target_url = data["audio_streams"][0].get("stream_url")

                # Fallback URL if JSON extraction failed
                if not target_url:
                    if video:
                        target_url = f"{API_URL}/api/stream_video?url=https://www.youtube.com/watch?v={video_id}&quality=338p"
                    else:
                        target_url = f"{API_URL}/api/stream_audio?url=https://www.youtube.com/watch?v={video_id}&format_id=140"

                logger.info(f"Downloading stream locally...")
                
                # 3. Download the file safely using chunks
                client_timeout = aiohttp.ClientTimeout(total=300, connect=15, sock_read=30)
                async with session.get(target_url, allow_redirects=True, timeout=client_timeout) as dl_resp:
                    if dl_resp.status not in (200, 206):
                        logger.error(f"API returned status {dl_resp.status} for URL {target_url}")
                        return None
                        
                    with open(file_path, "wb") as f:
                        async for chunk in dl_resp.content.iter_chunked(262144): # 256KB chunks
                            f.write(chunk)

            # 4. Return the valid LOCAL FILE PATH
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                logger.info(f"Successfully downloaded {video_id}! Ready to play.")
                return file_path
            else:
                logger.error(f"Downloaded file for {video_id} is empty.")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return None

        except asyncio.TimeoutError:
            logger.error(f"Download timed out for {video_id}.")
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
