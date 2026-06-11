import traceback
import random
from datetime import datetime, timedelta
import pytz
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
shipdb = db.shipping_list_single

async def get_ship(chat_id: int, date: str):
    data = await shipdb.find_one({"chat_id": chat_id, "date": date})
    if not data:
        return None
    return data.get("couple")

async def save_ship(chat_id: int, date: str, couple: dict):
    doc = {
        "chat_id": chat_id,
        "date": date,
        "couple": couple
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


# 1️⃣ MAIN SHIPPING COMMAND (1 Couple per day)
@app.on_message(filters.command(["ship", "shipping", "shipper", "ships"]))
async def shipping_cmd(_, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("Yᴇ ᴄᴏᴍᴍᴀɴᴅ sɪʀғ ɢʀᴏᴜᴘs ᴍᴇɪɴ ᴄʜᴀʟᴇɢᴀ ʙᴀʙʏ!")
        
    chat_id = message.chat.id
    today = get_date_by_delta(0)
    tomorrow = get_date_by_delta(1)
    
    try:
        # Check if today's couple is already selected
        saved_couple = await get_ship(chat_id, today)
        
        if not saved_couple:
            msg = await message.reply_text("🪄 **Fɪɴᴅɪɴɢ ᴛʜᴇ ʙᴇsᴛ ᴍᴀᴛᴄʜ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ...**")
            
            all_members = []
            async for member in app.get_chat_members(chat_id, limit=200):
                if not member.user.is_deleted:
                    all_members.append(member.user.mention)
                    
            if len(all_members) < 2:
                return await msg.edit("Gʀᴏᴜᴘ ᴍᴇɪɴ sᴜғғɪᴄɪᴇɴᴛ ᴍᴇᴍʙᴇʀs ɴᴀʜɪ ʜᴀɪɴ sʜɪᴘᴘɪɴɢ ᴋᴇ ʟɪʏᴇ!")
                
            random.shuffle(all_members)
            
            # Select only 1 couple
            u1 = all_members.pop()
            u2 = all_members.pop()
            
            couple_data = {
                "u1_mention": u1,
                "u2_mention": u2
            }
                
            # Save for exactly 24 hours
            await save_ship(chat_id, today, couple_data)
            await msg.delete()
        else:
            couple_data = saved_couple

        # Output Message
        text = f"💖 **Tᴏᴅᴀʏ's Bᴇsᴛ Cᴏᴜᴘʟᴇ** 💖\n\n"
        text += f"🌟 {couple_data['u1_mention']} + {couple_data['u2_mention']} = 💘\n"
        text += f"\nNᴇxᴛ sʜɪᴘᴘɪɴɢ ᴡɪʟʟ ʙᴇ ᴜᴘᴅᴀᴛᴇᴅ ᴏɴ {tomorrow}!!"
        
        await message.reply_text(
            text=text, 
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="Aᴅᴅ ᴍᴇ 🌋", url=f"https://t.me/{app.username}?startgroup=true")]
            ])
        )

    except Exception as e:
        print(f"🔥 SHIPPING CRASHED: {e}")
        traceback.print_exc()
        await message.reply_text("Kᴜᴄʜ ɢᴀʟᴛɪ ʜᴏ ɢᴀʏɪ ʙᴀʙʏ, ʙᴀᴀᴅ ᴍᴇɪɴ ᴛʀʏ ᴋᴀʀɴᴀ!")


# 2️⃣ LAST SHIPPING COMMAND (Fetches yesterday's 1 couple)
@app.on_message(filters.command(["last_shipping", "lastship"]))
async def last_shipping_cmd(_, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("Yᴇ ᴄᴏᴍᴍᴀɴᴅ sɪʀғ ɢʀᴏᴜᴘs ᴍᴇɪɴ ᴄʜᴀʟᴇɢᴀ ʙᴀʙʏ!")
        
    chat_id = message.chat.id
    yesterday = get_date_by_delta(-1)
    
    try:
        # Fetch yesterday's couple from database
        old_couple = await get_ship(chat_id, yesterday)
        
        if not old_couple:
            return await message.reply_text("😞 **Pɪᴄʜʟᴇ 𝟸𝟺 ɢʜᴀɴᴛᴏ ᴍᴇɪɴ ɪs ɢʀᴏᴜᴘ ᴍᴇɪɴ ᴋᴏɪ sʜɪᴘᴘɪɴɢ ɴᴀʜɪ ʜᴜɪ ᴛʜɪ!!**")
            
        text = f"⏳ **Lᴀsᴛ Sʜɪᴘᴘɪɴɢ Rᴇsᴜʟᴛ ({yesterday})** ⏳\n\n"
        text += f"🌟 {old_couple['u1_mention']} + {old_couple['u2_mention']} = 💘\n"
        text += f"\n▲ Yᴇ ᴘɪᴄʜʟᴇ ᴅɪɴ ᴋᴀ ʀᴇsᴜʟᴛ ʜᴀɪ. Nᴀʏᴀ ᴅᴇᴋʜɴᴇ ᴋᴇ ʟɪʏᴇ /shipping ᴛʏᴘᴇ ᴋᴀʀᴇɪɴ."
        
        await message.reply_text(
            text=text, 
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="Aᴅᴅ ᴍᴇ 🌋", url=f"https://t.me/{app.username}?startgroup=true")]
            ])
        )

    except Exception as e:
        print(f"🔥 LAST SHIPPING CRASHED: {e}")
        traceback.print_exc()
        await message.reply_text("Pɪᴄʜʟᴇ ʀᴇsᴜʟᴛs ɴɪᴋᴀʟɴᴇ ᴍᴇɪɴ ᴋᴜᴄʜ ᴘʀᴏʙʟᴇᴍ ʜᴜɪ!!")
        
