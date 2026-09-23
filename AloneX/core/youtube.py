#
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

    # STABLE & FAST: Direct info extraction + reliable chunked streaming
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

        # 30-second connection timeout, 5-minute total download timeout
        client_timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_read=30)

        try:
            async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
                target_url = None

                # STEP 1: Fetch stable direct link via JSON body
                logger.info(f"Fetching stable download stream for {video_id}...")
                async with session.post(
                    f"{API_URL}/api/info",
                    json={"input": f"https://youtu.be/{video_id}"}
                ) as info_resp:
                    if info_resp.status == 200:
                        data = await info_resp.json()
                        if video and data.get("mp4_formats"):
                            # Fast video setting: 480p or 360p
                            for fmt in data["mp4_formats"]:
                                if fmt.get("resolution") in ("480p", "360p"):
                                    target_url = fmt.get("download_url")
                                    break
                            if not target_url:
                                target_url = data["mp4_formats"][-1].get("download_url")
                        elif not video and data.get("audio_formats"):
                            # Fast audio setting: 192kbps or 128kbps
                            for fmt in data["audio_formats"]:
                                if fmt.get("quality") in ("192kbps", "128kbps"):
                                    target_url = fmt.get("download_url")
                                    break
                            if not target_url:
                                target_url = data["audio_formats"][0].get("download_url")

                # Fallback just in case JSON parsing failed
                if not target_url:
                    if video:
                        target_url = f"{API_URL}/mp4?video_id={video_id}&resolution=480"
                    else:
                        target_url = f"{API_URL}/audio?video_id={video_id}&quality=192"

                logger.info(f"Downloading stable stream... ({video_id})")

                # STEP 2: Download stream with active read timeout and 1MB chunks
                async with session.get(target_url, allow_redirects=True) as dl_resp:
                    if dl_resp.status not in (200, 206):
                        logger.error(f"Download stream returned status {dl_resp.status}")
                        return None

                    with open(file_path, "wb") as f:
                        while True:
                            # Massive chunk size for speed
                            chunk = await dl_resp.content.read(1048576)
                            if not chunk:
                                break
                            f.write(chunk)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 10240:
                logger.info(f"Successfully downloaded {video_id} ({os.path.getsize(file_path) // 1024} KB)")
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

