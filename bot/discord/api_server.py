import logging
import tempfile
from pathlib import Path

import disnake
from aiohttp import web

MAX_UPLOAD = 25 * 1024 * 1024


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except web.HTTPException as exc:
        return web.json_response({"error": exc.reason}, status=exc.status)
    except (ValueError, TypeError, UnicodeError):
        return web.json_response({"error": "Invalid request data."}, status=400)
    except disnake.Forbidden:
        return web.json_response({"error": "Bot lacks channel permissions."}, status=403)
    except disnake.NotFound:
        return web.json_response({"error": "Channel not found."}, status=404)
    except disnake.HTTPException:
        return web.json_response({"error": "Discord rejected the request."}, status=502)
    except Exception:
        logging.exception("API request failed")
        return web.json_response({"error": "Internal server error."}, status=500)


def create_app(bot):
    async def health(request):
        return web.json_response({"ready": bot.is_ready()})

    def require_ready():
        if not bot.is_ready():
            raise web.HTTPServiceUnavailable(reason="Discord bot is not connected yet.")

    async def channels(request):
        require_ready()
        return web.json_response({"servers": [
            {"id": str(g.id), "name": g.name, "channels": [
                {"id": str(c.id), "name": c.name}
                for c in g.text_channels
                if c.permissions_for(g.me).view_channel
                and c.permissions_for(g.me).send_messages
            ]} for g in bot.guilds
        ]})

    async def publish(request):
        require_ready()
        with tempfile.TemporaryFile() as upload:
            filename = None
            size = 0
            if request.content_type == "application/json":
                data = await request.json()
                if not isinstance(data, dict):
                    raise web.HTTPBadRequest(reason="Expected a JSON object.")
            elif request.content_type == "multipart/form-data":
                data = {}
                reader = await request.multipart()
                count = 0
                while (part := await reader.next()) is not None:
                    count += 1
                    if count > 3:
                        raise web.HTTPBadRequest(reason="Use channel_id, message and one media file.")
                    if part.name == "media" and part.filename:
                        if filename is not None:
                            raise web.HTTPBadRequest(reason="Only one media file is supported.")
                        filename = Path(part.filename.replace("\\", "/")).name or "upload"
                        while chunk := await part.read_chunk():
                            size += len(chunk)
                            if size > MAX_UPLOAD:
                                raise web.HTTPRequestEntityTooLarge(max_size=MAX_UPLOAD, actual_size=size)
                            upload.write(chunk)
                    elif part.name in ("channel_id", "message") and not part.filename:
                        value = bytearray()
                        while chunk := await part.read_chunk():
                            value.extend(chunk)
                            if len(value) > 8192:
                                raise web.HTTPBadRequest(reason="Form field is too long.")
                        data[part.name] = value.decode("utf-8")
                    else:
                        raise web.HTTPBadRequest(reason="Unknown multipart field.")
            else:
                raise web.HTTPUnsupportedMediaType(reason="Use JSON or multipart/form-data.")
            channel_id = data.get("channel_id")
            if not isinstance(channel_id, str) or not channel_id.isascii() or not channel_id.isdigit() or len(channel_id) > 20:
                raise web.HTTPBadRequest(reason="channel_id must be a Discord ID string.")
            message = data.get("message", "")
            if not isinstance(message, str) or len(message) > 2000:
                raise web.HTTPBadRequest(reason="message must be text of at most 2000 characters.")
            if not message.strip() and filename is None:
                raise web.HTTPBadRequest(reason="Provide message or media.")
            channel = bot.get_channel(int(channel_id))
            if not isinstance(channel, disnake.TextChannel):
                raise web.HTTPNotFound(reason="Choose a text channel from GET /channels.")
            permissions = channel.permissions_for(channel.guild.me)
            if not (permissions.view_channel and permissions.send_messages):
                raise web.HTTPForbidden(reason="Bot cannot send in that channel.")
            if filename is not None:
                if not permissions.attach_files:
                    raise web.HTTPForbidden(reason="Bot needs Attach Files permission.")
                if size > channel.guild.filesize_limit:
                    raise web.HTTPRequestEntityTooLarge(max_size=channel.guild.filesize_limit, actual_size=size)
                upload.seek(0)
                media = disnake.File(upload, filename=filename)
                try:
                    sent = await channel.send(content=message or None, file=media,
                                              allowed_mentions=disnake.AllowedMentions.none())
                finally:
                    media.close()
            else:
                sent = await channel.send(content=message, allowed_mentions=disnake.AllowedMentions.none())
            return web.json_response({"message_id": str(sent.id), "channel_id": str(channel.id),
                                      "url": sent.jump_url}, status=201)

    app = web.Application(middlewares=[errors], client_max_size=64 * 1024)
    app.add_routes([web.get('/health', health), web.get('/channels', channels),
                    web.post('/publish', publish)])
    return app


async def run(bot, token, host="127.0.0.1", port=8080):
    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
        print(f"Posting API: http://{host}:{port} (no authentication)")
        await bot.start(token)
    finally:
        await runner.cleanup()
        await bot.close()
