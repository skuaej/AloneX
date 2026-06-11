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

# -----------------------------------------------------------------
# LIVE TRACKING SYSTEM
# -----------------------------------------------------------------
ONGOING_SYNCS = []

@app.on_message(filters.command("total"))
async def cache_total(client: Client, message: Message):
    """Fetches the total count of cached media directly from MongoDB."""
    if cache_col is None:
        return await message.reply_text("❌ Database is not connected.")
    
    processing_msg = await message.reply_text("🔄 Fetching cache statistics...")
    
    try:
        total_audio = await cache_col.count_documents({"video": False})
        total_video = await cache_col.count_documents({"video": True})
        total = total_audio + total_video
        
        text = (
            f"📊 **Database Cache Statistics** 📊\n\n"
            f"🎵 **Audio Tracks:** `{total_audio}`\n"
            f"🎥 **Video Tracks:** `{total_video}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📁 **Total Media Cached:** `{total}`"
        )
        await processing_msg.edit_text(text)
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error fetching stats: {e}")

@app.on_message(filters.command("ongoing"))
async def cache_ongoing(client: Client, message: Message):
    """Shows the user which files are currently being processed."""
    if not ONGOING_SYNCS:
        return await message.reply_text("✅ No media is currently being synced. The queue is clear!")
    
    text = f"🔄 **Currently Syncing ({len(ONGOING_SYNCS)} items):**\n\n"
    for i, title in enumerate(ONGOING_SYNCS[:15], 1):
        text += f"{i}. `{title}`\n"
        
    if len(ONGOING_SYNCS) > 15:
        text += f"\n*...and {len(ONGOING_SYNCS) - 15} more in background.*"
        
    await message.reply_text(text)


# -----------------------------------------------------------------
# CORE CACHE LISTENER
# -----------------------------------------------------------------
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

    video_id = None
    if message.caption:
        lines = [line.strip() for line in message.caption.split("\n") if line.strip()]
        for line in lines:
            if len(line) == 11 and " " not in line and ":" not in line:
                video_id = line
                break

    # Extract clean meta-titles for indexing
    media_title = "Unknown Track"
    if message.audio and media.title:
        media_title = f"{media.performer} - {media.title}" if media.performer else media.title
    elif getattr(media, "file_name", None):
        media_title = ".".join(media.file_name.split(".")[:-1])

    # CPU SAVER: Check if we already saved this file by ID OR Title
    if video_id:
        existing = await cache_col.find_one({"video_id": video_id, "video": is_video})
        if existing:
            logger.info(f"⏭️ Skipped duplicate forward for Tracking ID: {video_id}")
            return
    else:
        # Check by title so raw forwarded MP3s aren't duplicated
        existing_title = await cache_col.find_one({"title": media_title.lower(), "video": is_video})
        if existing_title:
            logger.info(f"⏭️ Skipped duplicate file. Already exists in DB as: {existing_title.get('video_id')}")
            return

    if not video_id:
        random_hash = secrets.token_hex(4)
        video_id = f"vid_{random_hash}" if is_video else f"mp3_{random_hash}"
        format_str = "Video" if is_video else "Audio"
        
        try:
            new_caption = f"Saves: {format_str}\n{video_id}\n\nTitle: {media_title}"
            await message.edit_caption(caption=new_caption)
        except Exception:
            pass 

    # --- ADD TO LIVE TRACKER QUEUE ---
    tracker_name = f"[{video_id}] {media_title[:35]}"
    ONGOING_SYNCS.append(tracker_name)

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
    finally:
        # --- REMOVE FROM LIVE TRACKER QUEUE WHEN DONE ---
        if tracker_name in ONGOING_SYNCS:
            ONGOING_SYNCS.remove(tracker_name)
            
