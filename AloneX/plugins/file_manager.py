import os
import shutil
from pyrogram import filters
from pyrogram.types import Message
from AloneX import app
from AloneX.misc import SUDOERS

# --- 1. LIST DIRECTORY (/ls) ---
@app.on_message(filters.command(["ls", "dir"]) & filters.user(SUDOERS))
async def list_directory(client, message: Message):
    path = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else "."
    
    if not os.path.exists(path):
        return await message.reply_text(f"❌ **Error:** The path `{path}` does not exist.")
    
    if not os.path.isdir(path):
        return await message.reply_text(f"❌ **Error:** `{path}` is a file, not a directory.")

    try:
        items = os.listdir(path)
        items.sort()
        
        folders = [f"📁 `{item}`" for item in items if os.path.isdir(os.path.join(path, item))]
        files = [f"📄 `{item}`" for item in items if os.path.isfile(os.path.join(path, item))]
        
        output = f"**Contents of:** `{os.path.abspath(path)}`\n\n"
        output += "\n".join(folders) + "\n" + "\n".join(files)
        
        if not items:
            output += "*(Empty Directory)*"
            
        if len(output) > 4000:
            return await message.reply_text("❌ Output too long. Try a more specific directory.")
            
        await message.reply_text(output)
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

# --- 2. READ/OPEN FILE (/read) ---
@app.on_message(filters.command(["read", "cat", "open"]) & filters.user(SUDOERS))
async def read_file(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Please provide a file path. Example: `/read config.py`")
        
    path = message.text.split(maxsplit=1)[1]
    
    if not os.path.exists(path) or not os.path.isfile(path):
        return await message.reply_text(f"❌ **Error:** File `{path}` not found.")
        
    try:
        # Check size so we don't try to send massive files as text
        file_size = os.path.getsize(path)
        if file_size > 5 * 1024 * 1024:  # 5MB limit for direct reading
            return await message.reply_document(document=path, caption=f"📁 `{path}` is large. Sending as document.")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if len(content) > 4000:
            await message.reply_document(document=path, caption=f"📁 `{path}` (Sent as file because text is too long)")
        else:
            await message.reply_text(f"**Contents of `{path}`:**\n\n```python\n{content}\n```")
            
    except UnicodeDecodeError:
        # If it's a binary file (like an image or session file)
        await message.reply_document(document=path, caption=f"📁 `{path}` (Binary/Non-text file)")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

# --- 3. DELETE FILE OR FOLDER (/rm) ---
@app.on_message(filters.command(["rm", "delete"]) & filters.user(SUDOERS))
async def delete_file(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Please provide a file/folder path. Example: `/rm old_plugin.py`")
        
    path = message.text.split(maxsplit=1)[1]
    
    if not os.path.exists(path):
        return await message.reply_text(f"❌ **Error:** Path `{path}` not found.")
        
    try:
        if os.path.isfile(path):
            os.remove(path)
            await message.reply_text(f"✅ **Successfully deleted file:** `{path}`")
        elif os.path.isdir(path):
            shutil.rmtree(path)
            await message.reply_text(f"✅ **Successfully deleted directory and its contents:** `{path}`")
    except Exception as e:
        await message.reply_text(f"❌ **Error deleting `{path}`:** `{str(e)}`")

# --- 4. UPDATE/CREATE FILE (/update) ---
@app.on_message(filters.command(["update", "save"]) & filters.user(SUDOERS))
async def update_file(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Provide a file path. Example: `/update plugins/new_plugin.py`")
        
    if not message.reply_to_message:
        return await message.reply_text("❌ You must reply to a document/file or a text message to save it.")

    path = message.text.split(maxsplit=1)[1]
    
    try:
        if message.reply_to_message.document:
            status = await message.reply_text("📥 Downloading file to server...")
            await message.reply_to_message.download(file_name=path)
            await status.edit_text(f"✅ **Successfully updated/saved file at:** `{path}`")
            
        elif message.reply_to_message.text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(message.reply_to_message.text)
            await message.reply_text(f"✅ **Successfully written text to:** `{path}`")
            
        else:
            await message.reply_text("❌ Reply to a document or text message only.")
            
    except Exception as e:
        await message.reply_text(f"❌ **Error saving file:** `{str(e)}`")

# --- 5. CLEAR FOLDER CONTENTS (/clear) ---
@app.on_message(filters.command(["clear", "empty"]) & filters.user(SUDOERS))
async def clear_folder(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("❌ Please provide a folder path. Example: `/clear downloads`")
        
    path = message.text.split(maxsplit=1)[1]
    
    if not os.path.exists(path):
        return await message.reply_text(f"❌ **Error:** Path `{path}` not found.")
        
    if not os.path.isdir(path):
        return await message.reply_text(f"❌ **Error:** `{path}` is a file. Use `/rm` to delete files.")
        
    try:
        count_files = 0
        count_dirs = 0
        
        # Loop through everything inside the directory and delete it
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
                count_files += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                count_dirs += 1
                
        await message.reply_text(
            f"✅ **Successfully emptied:** `{path}`\n"
            f"🗑️ **Deleted:** `{count_files}` files and `{count_dirs}` sub-folders."
        )
    except Exception as e:
        await message.reply_text(f"❌ **Error clearing `{path}`:** `{str(e)}`")

__MODULE__ = "Sᴇʀᴠᴇʀ"
__HELP__ = """
**Server Management (SUDO ONLY):**

/ls [path] - List files in a directory.
/read [path] - Read a file's code or download it.
/rm [path] - Permanently delete a file or folder.
/clear [path] - Delete all contents INSIDE a folder without deleting the folder itself.
/update [path] - Reply to a document/text to replace/create a file.
"""
