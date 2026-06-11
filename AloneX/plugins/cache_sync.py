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

@app.on_message(filters.chat(config.CACHE_CHANNEL) & (filters.audio | filters.document))
async def auto_sync_forwarded_audio(client: Client, message: Message):
    """
    Listens continuously inside the storage channel. When audio files are uploaded 
    or forwarded in from external networks, it registers them directly to MongoDB.
    """
    if cache_col is None:
        return

    media = message.audio or message.document
    
    # Filter out documents that aren't valid audio format variants
    if message.document and not (media.mime_type and media.mime_type.startswith("audio/")):
        return

    # Extract clean meta-titles for indexing
    song_title = "Unknown Track"
    if message.audio:
        if media.title:
            song_title = f"{media.performer} - {media.title}" if media.performer else media.title
        elif media.file_name:
            song_title = ".".join(media.file_name.split(".")[:-1])
    elif message.document and media.file_name:
        song_title = ".".join(media.file_name.split(".")[:-1])

    # Scan the message caption to see if it already contains an 11-character tracking ID
    video_id = None
    if message.caption:
        lines = [line.strip() for line in message.caption.split("\n") if line.strip()]
        for line in lines:
            if len(line) == 11 and " " not in line and ":" not in line:
                video_id = line
                break

    # If it is a raw file forward without an explicit ID, build a custom tracked ID reference
    if not video_id:
        random_hash = secrets.token_hex(4)
        video_id = f"mp3_{random_hash}"
        
        # Inject tracking markers into the channel caption structure
        try:
            new_caption = f"Saves:\n{video_id}\n\n{video_id}\nTitle: {song_title}"
            await message.edit_caption(caption=new_caption)
        except Exception:
            pass # Fails gracefully if the client missing author modification permissions

    # Commit the record index natively into MongoDB 
    try:
        await cache_col.update_one(
            {"video_id": video_id},
            {
                "$set": {
                    "message_id": message.id,
                    "title": song_title.lower(),
                    "video": False
                }
            },
            upsert=True
        )
        logger.info(f"Successfully tracked and saved MP3 file asset: '{song_title}' with Tracking ID: {video_id}")
    except Exception as err:
        logger.error(f"Error writing to MongoDB in sync interceptor module: {err}")
        
