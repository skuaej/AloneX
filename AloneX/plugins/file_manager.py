import os
import shutil
from pyrogram import filters
from pyrogram.types import Message
from AloneX import app
from config import Config

# Initialize your config to safely grab the OWNER_ID (8827902968)
cfg = Config()
OWNER_ID = cfg.OWNER_ID

# --- 1. LIST DIRECTORY (/ls) ---
@app.on_message(filters.command(["ls", "dir"]) & filters.user(OWNER_ID))
async def list_directory(client, message: Message):
    path = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else "."
    
    if not os.path.exists(path):
        return await message.reply_text(f"❌ **Error:** Path `{path}` doesn't exist.")
    
    try:
        items = os.listdir(path)
        items.sort()
        
        folders = [f"📁 `{item}`" for item in items if os.path.isdir(os.path.join(path, item))]
        files = [f"📄 `{item}`" for item in items if os.path.isfile(os.path.join(path, item))]

        output = f"**Contents of:** `{os.path.abspath(path)}`\n\n" + "\n".join(folders) + "\n" + "\n".join(files)
        
        if len(output) > 4000:
            return await message.reply_text("❌ Output too long. Try a more specific directory.")
            
        await message.reply_text(output if items else "*(Empty Directory)*")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

# --- 2. READ/OPEN FILE (/read) ---
@app.on_message(filters.command(["read", "cat", "open"]) & filters.user(OWNER_ID))
async def read_file(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Provide a file path. Example: `/read config.py`")
        
    path = message.text.split(maxsplit=1)[1]

    if not os.path.exists(path) or not os.path.isfile(path):
        return await message.reply_text("❌ File not found.")
        
    try:
        if os.path.getsize(path) > 5 * 1024 * 1024:
            return await message.reply_document(document=path, caption=f"📁 Sending large file.")
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if len(content) > 4000:
            await message.reply_document(document=path, caption=f"📁 `{path}`")
        else:
            await message.reply_text(f"```python\n{content}\n```")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

# --- 3. DELETE FILE OR FOLDER (/rm) ---
@app.on_message(filters.command(["rm", "delete"]) & filters.user(OWNER_ID))
async def delete_file(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Provide a path. Example: `/rm old_plugin.py`")
        
    path = message.text.split(maxsplit=1)[1]

    try:
        if os.path.isfile(path):
            os.remove(path)
            await message.reply_text(f"✅ Deleted file: `{path}`")
        elif os.path.isdir(path):
            shutil.rmtree(path)
            await message.reply_text(f"✅ Deleted directory: `{path}`")
        else:
            await message.reply_text("❌ Path not found.")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

# --- 4. UPDATE/CREATE FILE (/update) ---
@app.on_message(filters.command(["update", "save"]) & filters.user(OWNER_ID))
async def update_file(client, message: Message):
    if len(message.command) < 2 or not message.reply_to_message:
        return await message.reply_text("❌ Reply to a document/text with `/update [path]`")
        
    path = message.text.split(maxsplit=1)[1]

    try:
        if message.reply_to_message.document:
            status = await message.reply_text("📥 Downloading...")
            await message.reply_to_message.download(file_name=path)
            await status.edit_text(f"✅ Updated file at: `{path}`")
        elif message.reply_to_message.text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(message.reply_to_message.text)
            await message.reply_text(f"✅ Written text to: `{path}`")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

# --- 5. CLEAR FOLDER CONTENTS (/clear) ---
@app.on_message(filters.command(["clear", "empty"]) & filters.user(OWNER_ID))
async def clear_folder(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Provide a folder path. Example: `/clear downloads`")
        
    path = message.text.split(maxsplit=1)[1]

    if not os.path.exists(path) or not os.path.isdir(path):
        return await message.reply_text("❌ Folder not found.")
        
    try:
        f_count, d_count = 0, 0
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
                f_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                d_count += 1
        await message.reply_text(f"✅ Emptied `{path}` (Deleted {f_count} files, {d_count} folders).")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

__MODULE__ = "Sᴇʀᴠᴇʀ"
__HELP__ = """
**Server Management (OWNER ONLY):**
/ls [path] - List folder items.
/read [path] - Read file code or download it.
/rm [path] - Delete file/folder.
/clear [path] - Wipe folder contents cleanly.
/update [path] - Overwrite path with replied text/file.
"""
