from datetime import datetime, timedelta
import pytz
import os
import random
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatType
from PIL import Image, ImageDraw
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Import app and config from your AloneX bot
from AloneX import app, config

# ==========================================
# 🗄️ DATABASE SYSTEM FOR COUPLES
# ==========================================
mongo_client = AsyncIOMotorClient(config.MONGO_URL)
db = mongo_client.AloneX
coupledb = db.couples

async def get_image(chat_id: int):
    couple = await coupledb.find_one({"chat_id": chat_id})
    if not couple:
        return None
    return couple.get("b_img")

async def get_couple(chat_id: int, date: str):
    couple = await coupledb.find_one({"chat_id": chat_id, "date": date})
    if not couple:
        return False
    return couple.get("couple")

async def save_couple(chat_id: int, date: str, couple: dict, img: str):
    new_couple = {
        "chat_id": chat_id,
        "date": date,
        "couple": couple,
        "b_img": img
    }
    await coupledb.update_one(
        {"chat_id": chat_id},
        {"$set": new_couple},
        upsert=True
    )
# ==========================================

def get_today_date():
    timezone = pytz.timezone("Asia/Kolkata")
    now = datetime.now(timezone)
    return now.strftime("%d/%m/%Y")

def get_todmorrow_date():
    timezone = pytz.timezone("Asia/Kolkata")
    tomorrow = datetime.now(timezone) + timedelta(days=1)
    return tomorrow.strftime("%d/%m/%Y")

def download_image(url, path):
    response = requests.get(url)
    if response.status_code == 200:
        with open(path, "wb") as f:
            f.write(response.content)
    return path


@app.on_message(filters.command(["couple", "couples"]))
async def ctest(_, message):
    cid = message.chat.id
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("Tʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ᴡᴏʀᴋs ɪɴ ɢʀᴏᴜᴘs.")

    os.makedirs("downloads", exist_ok=True)

    # Unique names so they don't overwrite if multiple groups use it at once
    p1_path = f"downloads/pfp1_{cid}.png"
    p2_path = f"downloads/pfp2_{cid}.png"
    test_image_path = f"downloads/test_{cid}.png"
    cppic_path = f"downloads/cppic_{cid}.png"

    try:
        is_selected = await get_couple(cid, today)
        
        if not is_selected:
            msg = await message.reply_text("❣️ **Gᴇɴᴇʀᴀᴛɪɴɢ Cᴏᴜᴘʟᴇ...**")
            list_of_users = []

            async for i in app.get_chat_members(message.chat.id, limit=50):
                if not i.user.is_bot and not i.user.is_deleted:
                    list_of_users.append(i.user.id)

            if len(list_of_users) < 2:
                return await msg.edit("Gʀᴏᴜᴘ ᴍᴇɪɴ sᴜғғɪᴄɪᴇɴᴛ ᴍᴇᴍʙᴇʀs ɴᴀʜɪ ʜᴀɪɴ!!")

            c1_id = random.choice(list_of_users)
            c2_id = random.choice(list_of_users)
            while c1_id == c2_id:
                c1_id = random.choice(list_of_users)

            photo1 = (await app.get_chat(c1_id)).photo
            photo2 = (await app.get_chat(c2_id)).photo

            N1 = (await app.get_users(c1_id)).mention
            N2 = (await app.get_users(c2_id)).mention

            try:
                p1 = await app.download_media(photo1.big_file_id, file_name=p1_path)
            except Exception:
                p1 = download_image("https://telegra.ph/file/05aa686cf52fc666184bf.jpg", p1_path)
            try:
                p2 = await app.download_media(photo2.big_file_id, file_name=p2_path)
            except Exception:
                p2 = download_image("https://telegra.ph/file/05aa686cf52fc666184bf.jpg", p2_path)

            img1 = Image.open(p1)
            img2 = Image.open(p2)

            background_image_path = download_image("https://telegra.ph/file/96f36504f149e5680741a.jpg", cppic_path)
            img = Image.open(background_image_path)

            img1 = img1.resize((437, 437))
            img2 = img2.resize((437, 437))

            mask = Image.new("L", img1.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + img1.size, fill=255)

            mask1 = Image.new("L", img2.size, 0)
            draw = ImageDraw.Draw(mask1)
            draw.ellipse((0, 0) + img2.size, fill=255)

            img1.putalpha(mask)
            img2.putalpha(mask1)

            draw = ImageDraw.Draw(img)
            img.paste(img1, (116, 160), img1)
            img.paste(img2, (789, 160), img2)
            img.save(test_image_path)

            TXT = f"""
<b>Tᴏᴅᴀʏ's ᴄᴏᴜᴘʟᴇ ᴏғ ᴛʜᴇ ᴅᴀʏ:

{N1} + {N2} = 💚

Nᴇxᴛ ᴄᴏᴜᴘʟᴇs ᴡɪʟʟ ʙᴇ sᴇʟᴇᴄᴛᴇᴅ ᴏɴ {tomorrow}!!</b>
            """

            # 🚀 TELEGRAM DIRECT UPLOAD
            sent_message = await message.reply_photo(
                test_image_path,
                caption=TXT,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="Aᴅᴅ ᴍᴇ 🌋", url=f"https://t.me/{app.username}?startgroup=true")]
                ])
            )
            await msg.delete()
            
            # 🔥 Save Telegram's exact file_id instead of Telegraph Link
            file_id = sent_message.photo.file_id
            couple = {"c1_id": c1_id, "c2_id": c2_id}
            await save_couple(cid, today, couple, file_id)

        else:
            msg = await message.reply_text("❣️")
            b_img_id = await get_image(cid)
            c1_id = int(is_selected["c1_id"])
            c2_id = int(is_selected["c2_id"])
            c1_name = (await app.get_users(c1_id)).first_name
            c2_name = (await app.get_users(c2_id)).first_name

            TXT = f"""
<b>Tᴏᴅᴀʏ's ᴄᴏᴜᴘʟᴇ ᴏғ ᴛʜᴇ ᴅᴀʏ 🎉:

<a href="tg://openmessage?user_id={c1_id}">{c1_name}</a> + <a href="tg://openmessage?user_id={c2_id}">{c2_name}</a> = ❣️

Nᴇxᴛ ᴄᴏᴜᴘʟᴇs ᴡɪʟʟ ʙᴇ sᴇʟᴇᴄᴛᴇᴅ ᴏɴ {tomorrow}!!</b>
            """
            await message.reply_photo(
                photo=b_img_id, # Reusing the Telegram file_id directly!
                caption=TXT,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="Aᴅᴅ ᴍᴇ 🌋", url=f"https://t.me/{app.username}?startgroup=true")]
                ])
            )
            await msg.delete()

    except Exception as e:
        print(f"Couples Error: {e}")
    finally:
        # Clean up all temporary files safely
        for file in [p1_path, p2_path, test_image_path, cppic_path]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception:
                    pass
                    
