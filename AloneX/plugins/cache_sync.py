import secrets
from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
from AloneX import app, config, logger

# Initialize database connections safely inside the plugin module
cache_col = None
if hasattr(config, "MONGO_URL") and config.MONGO_URL:
    try:
        mongo_client = AsyncIOMotorClient(config.MONGO_URL)
        db = mongo_client["AloneX_Cloud_Cache"]
        cache_col = db["tracks"]
    except Exception as e:
        logger.error(f"Failed syncing MongoDB instance inside Sync plugin: {e}")

@app.on_message(filters.chat(config.CACHE_CHANNEL) & (filters.audio | filters.document))
async def auto_sync_forwarded_audio(client: Client, message: Message):
    """
    Automatically intercept and map any forwarded or uploaded audio file inside 
    the cloud cache storage channel into your permanent MongoDB collection.
    """
    if cache_col is None:
        return

    media = message.audio or message.document
    
    # Ensure it's actually an MP3 or audio asset container
    if message.document and not (media.mime_type and media.mime_type.startswith("audio/")):
        return

    # Extract clean title from metadata structures or fallback to file name
    song_title = "Unknown Track"
    if message.audio:
        if media.title:
            song_title = f"{media.performer} - {media.title}" if media.performer else media.title
        elif media.file_name:
            song_title = ".".join(media.file_name.split(".")[:-1])
    elif message.document and media.file_name:
        song_title = ".".join(media.file_name.split(".")[:-1])

    # Check if this file already has a YouTube/Cache ID in its caption string
    video_id = None
    if message.caption:
        # Match lines that look like a unique 11 character id string
        lines = [line.strip() for line in message.caption.split("\n") if line.strip()]
        for line in lines:
            if len(line) == 11 and " " not in line and ":" not in line:
                video_id = line
                break

    # If it's a raw forwarded MP3 without a tracking tag, generate a unique ID
    if not video_id:
        random_hash = secrets.token_hex(4)  # 8 characters hash
        video_id = f"mp3_{random_hash}"
        
        # Add the tracking caption to the message so your userbots can search it if necessary
        try:
            new_caption = f"Saves:\n{video_id}\n\n{video_id}\nTitle: {song_title}"
            await message.edit_caption(caption=new_caption)
        except Exception:
            pass  # Non-author accounts might not have permissions to edit captions

    # Commit straight into MongoDB collection index
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
        logger.error(f"Error executing collection save in sync interceptor: {err}")
      
