from datetime import datetime, timedelta
import pytz
import random
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatType
from motor.motor_asyncio import AsyncIOMotorClient

# Import app and config from your AloneX bot
from AloneX import app, config

# ==========================================
# 🗄️ DATABASE SYSTEM FOR SHIPPING
# ==========================================
mongo_client = AsyncIOMotorClient(config.MONGO_URL)
db = mongo_client.AloneX
shipdb = db.shipping_list

async def get_ships(chat_id: int, date: str):
    data = await shipdb.find_one({"chat_id": chat_id, "date": date})
    if not data:
        return None
    return data.get("ships")

async def save_ships(chat_id: int, date: str, ships: list):
    doc = {
        "chat_id": chat_id,
        "date": date,
        "ships": ships
    }
    await shipdb.update_one(
        {"chat_id": chat_id, "date": date},
        {"$set": doc},
        upsert=True
    )
# ==========================================

def get_date_by_delta(days_delta: int):
    timezone = pytz.timezone("Asia/Kolkata")
    target_date = datetime.now(timezone) + timedelta(days=days_delta)
    return target_date.strftime("%d/%m/%Y")


# 1️⃣ MAIN SHIPPING COMMAND (On-going for today)
@app.on_message(filters.command(["ship", "shipping", "shipper", "ships"]))
async def shipping_cmd(_, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("Yᴇ ᴄᴏᴍᴍᴀɴᴅ sɪʀғ ɢʀᴏᴜᴘs ᴍᴇɪɴ ᴄʜᴀʟᴇɢᴀ ʙᴀʙʏ!")
        
    chat_id = message.chat.id
    today = get_date_by_delta(0)
    tomorrow = get_date_by_delta(1)
    
    try:
        # Check if ships are already generated for today
        saved_ships = await get_ships(chat_id, today)
        
        if not saved_ships:
            msg = await message.reply_text("🪄 **Fɪɴᴅɪɴɢ ᴛʜᴇ ʙᴇsᴛ ᴍᴀᴛᴄʜᴇs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ...**")
            
            members = []
            async for member in app.get_chat_members(chat_id, limit=100):
                if not member.user.is_bot and not member.user.is_deleted:
                    members.append(member.user.mention)
                    
            if len(members) < 2:
                return await msg.edit("Gʀᴏᴜᴘ ᴍᴇɪɴ sᴜғғɪᴄɪᴇɴᴛ ᴍᴇᴍʙᴇʀs ɴᴀʜɪ ʜᴀɪɴ sʜɪᴘᴘɪɴɢ ᴋᴇ ʟɪʏᴇ!")
                
            random.shuffle(members)
            
            ships = []
            for _ in range(5):
                if len(members) < 2:
                    break
                u1 = members.pop()
                u2 = members.pop()
                ships.append(f"{u1} + {u2}")
                
            await save_ships(chat_id, today, ships)
            await msg.delete()
        else:
            ships = saved_ships

        emojis = ["💘", "💝", "💖", "💗", "💓"]
        text = f"💖 **Tᴏᴘ Sʜɪᴘs Oғ Tʜᴇ Dᴀʏ (Oɴ-ɢᴏɪɴɢ)** 💖\n\n"
        
        for i, ship in enumerate(ships):
            emoji = emojis[i] if i < len(emojis) else "✨"
            text += f"**{i+1}.** {ship} = {emoji}\n"
            
        text += f"\nNᴇxᴛ sʜɪᴘᴘɪɴɢ ᴡɪʟʟ ʙᴇ ᴜᴘᴅᴀᴛᴇᴅ ᴏɴ {tomorrow}!!"
        
        await message.reply_text(text=text, disable_web_page_preview=True)

    except Exception as e:
        print(f"Shipping Error: {e}")
        await message.reply_text("Kᴜᴄʜ ɢᴀʟᴛɪ ʜᴏ ɢᴀʏɪ ʙᴀʙʏ, ʙᴀᴀᴅ ᴍᴇɪɴ ᴛʀʏ ᴋᴀʀɴᴀ!")


# 2️⃣ LAST SHIPPING COMMAND (Fetches yesterday's results)
@app.on_message(filters.command(["last_shipping", "lastship"]))
async def last_shipping_cmd(_, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("Yᴇ ᴄᴏᴍᴍᴀɴᴅ sɪʀғ ɢʀᴏᴜᴘs ᴍᴇɪɴ ᴄʜᴀʟᴇɢᴀ ʙᴀʙʏ!")
        
    chat_id = message.chat.id
    yesterday = get_date_by_delta(-1)
    
    try:
        # Fetch yesterday's list from database
        old_ships = await get_ships(chat_id, yesterday)
        
        if not old_ships:
            return await message.reply_text("😞 **Pɪᴄʜʟᴇ 𝟸𝟺 ɢʜᴀɴᴛᴏ ᴍᴇɪɴ ɪs ɢʀᴏᴜᴘ ᴍᴇɪɴ ᴋᴏɪ sʜɪᴘᴘɪɴɢ ɴᴀʜɪ ʜᴜɪ sɪ̨!!**")
            
        emojis = ["💘", "💝", "💖", "💗", "💓"]
        text = f"⏳ **Lᴀsᴛ Sʜɪᴘᴘɪɴɢ Rᴇsᴜʟᴛs ({yesterday})** ⏳\n\n"
        
        for i, ship in enumerate(old_ships):
            emoji = emojis[i] if i < len(emojis) else "✨"
            text += f"**{i+1}.** {ship} = {emoji}\n"
            
        text += f"\n▲ Yᴇ ᴘɪᴄʜʟᴇ ᴅɪɴ ᴋᴀ ʀᴇsᴜʟᴛ ʜᴀɪ. Nᴀʏᴀ ᴅᴇᴋʜɴᴇ ᴋᴇ ʟɪʏᴇ /shipping ᴛʏᴘᴇ ᴋᴀʀᴇɪɴ."
        
        await message.reply_text(text=text, disable_web_page_preview=True)

    except Exception as e:
        print(f"Last Shipping Error: {e}")
        await message.reply_text("Pɪᴄʜʟᴇ ʀᴇsᴜʟᴛs ɴɪᴋᴀʟɴᴇ ᴍᴇɪɴ ᴋᴜᴄʜ ᴘʀᴏʙʟᴇᴍ ʜᴜɪ!!")

