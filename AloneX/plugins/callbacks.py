# Copyright (c) 2025 TheHamkerAlone
# Licensed under the MIT License.
# This file is part of AloneXMusic
# ALONE-CODER

import re

from pyrogram import filters, types

from AloneX import anon, app, db, lang, queue, tg, yt
from AloneX.helpers import admin_check, buttons, can_manage_vc


@app.on_callback_query(filters.regex("cancel_dl") & ~app.bl_users)
@lang.language()
async def cancel_dl(_, query: types.CallbackQuery):
    await query.answer()
    await tg.cancel(query)


@app.on_callback_query(filters.regex("controls") & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _controls(_, query: types.CallbackQuery):
    args = query.data.split()
    action, chat_id = args[1], int(args[2])
    qaction = len(args) == 4
    user = query.from_user.mention

    if not await db.get_call(chat_id):
        return await query.answer(query.lang["not_playing"], show_alert=True)

    if action == "status":
        return await query.answer()

    if action == "pause":
        await query.answer(query.lang["processing"], show_alert=True)
        if not await db.playing(chat_id):
            return await query.answer(
                query.lang["play_already_paused"], show_alert=True
            )
        await anon.pause(chat_id)
        if qaction:
            return await query.edit_message_reply_markup(
                reply_markup=buttons.queue_markup(chat_id, query.lang["paused"], False)
            )
        status = query.lang["paused"]
        reply = query.lang["play_paused"].format(user)

    elif action == "resume":
        await query.answer(query.lang["processing"], show_alert=True)
        if await db.playing(chat_id):
            return await query.answer(query.lang["play_not_paused"], show_alert=True)
        await anon.resume(chat_id)
        if qaction:
            return await query.edit_message_reply_markup(
                reply_markup=buttons.queue_markup(chat_id, query.lang["playing"], True)
            )
        reply = query.lang["play_resumed"].format(user)

    elif action == "skip":
        await query.answer(query.lang["processing"], show_alert=True)
        await anon.play_next(chat_id)
        status = query.lang["skipped"]
        reply = query.lang["play_skipped"].format(user)

    elif action == "seekforward":
        if not await db.playing(chat_id):
            return await query.answer(query.lang["play_already_paused"], show_alert=True)
        
        media = queue.get_current(chat_id)
        if not media.duration_sec:
            return await query.answer(query.lang["play_seek_no_dur"], show_alert=True)
            
        start_from = media.time + 20
        
        # Smart skipping if +20s reaches the end of the song
        if start_from >= media.duration_sec:
            await query.answer("Reached the end! Skipping to next...", show_alert=False)
            await anon.play_next(chat_id) 
            action = "skip" 
            status = query.lang["skipped"]
            reply = f"⏭ Skipped to next track by {user} (Fast Forward reached end)"
        else:
            await query.answer("Fast Forwarding 20s...", show_alert=False)
            await anon.play_media(chat_id, query.message, media, start_from)
            media.time = start_from
            status = "Seeked Forward"
            reply = f"⏩ Fast forwarded by {user}"

    elif action == "seekback":
        if not await db.playing(chat_id):
            return await query.answer(query.lang["play_already_paused"], show_alert=True)
        
        media = queue.get_current(chat_id)
        if not media.duration_sec:
            return await query.answer(query.lang["play_seek_no_dur"], show_alert=True)
            
        start_from = media.time - 20
        if start_from < 1:
            start_from = 1

        await query.answer("Rewinding 20s...", show_alert=False)
        await anon.play_media(chat_id, query.message, media, start_from)
        media.time = start_from
        status = "Seeked Backward"
        reply = f"⏪ Rewound by {user}"

    elif action == "force":
        await query.answer(query.lang["processing"], show_alert=True)
        pos, media = queue.check_item(chat_id, args[3])
        if not media or pos == -1:
            return await query.edit_message_text(query.lang["play_expired"])

        m_id = queue.get_current(chat_id).message_id
        queue.force_add(chat_id, media, remove=pos)
        try:
            await app.delete_messages(
                chat_id=chat_id, message_ids=[m_id, media.message_id], revoke=True
            )
            media.message_id = None
        except:
            pass

        msg = await app.send_message(chat_id=chat_id, text=query.lang["play_next"])
        if not media.file_path:
            media.file_path = await yt.download(media.id, video=media.video)
        media.message_id = msg.id
        return await anon.play_media(chat_id, msg, media)

    elif action == "replay":
        await query.answer(query.lang["processing"], show_alert=True)
        media = queue.get_current(chat_id)
        media.user = user
        await anon.replay(chat_id)
        status = query.lang["replayed"]
        reply = query.lang["play_replayed"].format(user)

    elif action == "stop":
        await query.answer(query.lang["processing"], show_alert=True)
        await anon.stop(chat_id)
        status = query.lang["stopped"]
        reply = query.lang["play_stopped"].format(user)

    try:
        if action in ["skip", "replay", "stop"]:
            await query.message.reply_text(reply, quote=False)
            await query.message.delete()
        elif action in ["seekforward", "seekback", "pause", "resume"]:
            mtext = re.sub(
                r"\n\n<blockquote>.*?</blockquote>",
                "",
                query.message.caption.html or query.message.text.html,
                flags=re.DOTALL,
            )
            keyboard = buttons.controls(
                chat_id, status=status if action != "resume" else None
            )
            await query.edit_message_text(
                f"{mtext}\n\n<blockquote>{reply}</blockquote>", reply_markup=keyboard
            )
    except:
        pass


@app.on_callback_query(filters.regex(r"^help(_back_start| back| close| \w+)?$") & ~app.bl_users)
@lang.language()
async def _help(_, query: types.CallbackQuery):
    data = query.data.split()

    if query.data == "help_back_start":
        _text = query.lang["start_pm"].format(query.from_user.first_name, app.name)
        return await query.edit_message_text(
            text=_text,
            reply_markup=buttons.start_key(query.lang, True)
        )

    if len(data) == 1:
        return await query.edit_message_text(
            text=query.lang["help_menu"],
            reply_markup=buttons.help_markup(query.lang)
        )

    if data[1] == "back":
        return await query.edit_message_text(
            text=query.lang["help_menu"], reply_markup=buttons.help_markup(query.lang)
        )
    elif data[1] == "close":
        try:
            await query.message.delete()
            return await query.message.reply_to_message.delete()
        except:
            pass

    await query.edit_message_text(
        text=query.lang[f"help_{data[1]}"],
        reply_markup=buttons.help_markup(query.lang, True),
    )


@app.on_callback_query(filters.regex("settings") & ~app.bl_users)
@lang.language()
@admin_check
async def _settings_cb(_, query: types.CallbackQuery):
    cmd = query.data.split()
    if len(cmd) == 1:
        return await query.answer()
    await query.answer(query.lang["processing"], show_alert=True)

    chat_id = query.message.chat.id
    _admin = await db.get_play_mode(chat_id)
    _delete = await db.get_cmd_delete(chat_id)
    _language = await db.get_lang(chat_id)

    if cmd[1] == "delete":
        _delete = not _delete
        await db.set_cmd_delete(chat_id, _delete)
    elif cmd[1] == "play":
        await db.set_play_mode(chat_id, _admin)
        _admin = not _admin
    await query.edit_message_reply_markup(
        reply_markup=buttons.settings_markup(
            query.lang,
            _admin,
            _delete,
            _language,
            chat_id,
        )
    )


@app.on_callback_query(filters.regex("^close$") & ~app.bl_users)
async def close_menu(_, query: types.CallbackQuery):
    try:
        await query.answer()
        # Grabs the name of the user who clicked it
        user = query.from_user.mention 
        
        # Deletes the big player message
        await query.message.delete()
        if query.message.reply_to_message:
            await query.message.reply_to_message.delete()
            
        # Sends the custom closed message
        await app.send_message(
            chat_id=query.message.chat.id,
            text=f"𝐒ᴛʀᴇᴀᴍ Closed  𝐁ʏ {user}"
        )
    except:
        pass
