import secrets
from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from AloneX import app, config, logger

# Initialize localized database hooks for fast access inside the plugin
cache_col = None
if hasattr(config, "MONGO_URL") and config.MONGO_URL:
    try:
        mongo_client = AsyncIOMotorClient(config.MONGO_URL)
        db = mongo_client["AloneX_Cloud_Cache"]
        cache_col = db["tracks"]
    except Exception as e:
        logger.error(f"Failed mapping MongoDB pipeline in Sync module: {e}")

# Build a list of the separated channels to monitor
CACHE_CHANNELS = []
if getattr(config, "AUDIO_CACHE_CHANNEL", None):
    CACHE_CHANNELS.append(config.AUDIO_CACHE_CHANNEL)
if getattr(config, "VIDEO_CACHE_CHANNEL", None):
    CACHE_CHANNELS.append(config.VIDEO_CACHE_CHANNEL)

# Listen to both channels for Audio, Video, or Document uploads
@app.on_message(filters.chat(CACHE_CHANNELS) & (filters.audio | filters.video | filters.document))
async def auto_sync_forwarded_media(client: Client, message: Message):
    if cache_col is None or not CACHE_CHANNELS:
        return

    is_video = False
    media = None

    if message.video:
        media = message.video
        is_video = True
    elif message.audio:
        media = message.audio
    elif message.document:
        media = message.document
        if media.mime_type:
            if media.mime_type.startswith("video/"):
                is_video = True
            elif not media.mime_type.startswith("audio/"):
                return
        else:
            return

    # Scan the message caption to see if it already contains an 11-character tracking ID
    video_id = None
    if message.caption:
        lines = [line.strip() for line in message.caption.split("\n") if line.strip()]
        for line in lines:
            if len(line) == 11 and " " not in line and ":" not in line:
                video_id = line
                break

    # CPU SAVER: If the forwarded file already has an ID, check if we already saved it. 
    # If it exists, SKIP it completely!
    if video_id:
        existing = await cache_col.find_one({"video_id": video_id, "video": is_video})
        if existing:
            logger.info(f"⏭️ Skipped duplicate forward for Tracking ID: {video_id}")
            return

    # Extract clean meta-titles for indexing
    media_title = "Unknown Track"
    if message.audio and media.title:
        media_title = f"{media.performer} - {media.title}" if media.performer else media.title
    elif getattr(media, "file_name", None):
        media_title = ".".join(media.file_name.split(".")[:-1])

    # If it is a raw file forward without an explicit ID, build a custom tracked ID reference
    if not video_id:
        random_hash = secrets.token_hex(4)
        video_id = f"vid_{random_hash}" if is_video else f"mp3_{random_hash}"
        format_str = "Video" if is_video else "Audio"
        
        try:
            new_caption = f"Saves: {format_str}\n{video_id}\n\nTitle: {media_title}"
            await message.edit_caption(caption=new_caption)
        except Exception:
            pass 

    try:
        await cache_col.update_one(
            {"video_id": video_id, "video": is_video},
            {
                "$set": {
                    "message_id": message.id,
                    "title": media_title.lower(),
                    "video": is_video
                }
            },
            upsert=True
        )
        format_log = "Video" if is_video else "Audio"
        logger.info(f"✅ Successfully tracked and saved {format_log} asset: '{media_title}' with Tracking ID: {video_id}")
    except Exception as err:
        logger.error(f"Error writing to MongoDB in sync interceptor module: {err}")
        
