import logging
from contextlib import closing

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
    """Internal API; the parent application owns access control and bot startup."""
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
        if request.content_type == "application/json":
            data = await request.json()
            if not isinstance(data, dict):
                raise web.HTTPBadRequest(reason="Expected a JSON object.")
        elif request.content_type == "multipart/form-data":
            data = await request.post()
        else:
            raise web.HTTPUnsupportedMediaType(reason="Use JSON or multipart/form-data.")

        channel_id = data.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id.isdecimal():
            raise web.HTTPBadRequest(reason="channel_id must be a Discord ID string.")
        message = data.get("message", "")
        media = data.get("media")
        if not isinstance(message, str) or len(message) > 2000:
            raise web.HTTPBadRequest(reason="message must be text of at most 2000 characters.")
        if media is not None and not isinstance(media, web.FileField):
            raise web.HTTPBadRequest(reason="media must be an uploaded file.")
        if not message.strip() and media is None:
            raise web.HTTPBadRequest(reason="Provide message or media.")

        channel = bot.get_channel(int(channel_id))
        if not isinstance(channel, disnake.TextChannel):
            raise web.HTTPNotFound(reason="Choose a text channel from GET /channels.")
        kwargs = {"content": message or None, "allowed_mentions": disnake.AllowedMentions.none()}
        if media is not None:
            size = media.file.seek(0, 2)
            limit = min(MAX_UPLOAD, channel.guild.filesize_limit)
            if size > limit:
                raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=size)
            media.file.seek(0)
            with closing(disnake.File(media.file, filename=media.filename)) as file:
                sent = await channel.send(**kwargs, file=file)
        else:
            sent = await channel.send(**kwargs)
        return web.json_response({"message_id": str(sent.id), "channel_id": str(channel.id),
                                  "url": sent.jump_url}, status=201)

    app = web.Application(middlewares=[errors], client_max_size=MAX_UPLOAD)
    app.add_routes([web.get('/health', health), web.get('/channels', channels),
                    web.post('/publish', publish)])
    return app


async def run(bot, token, host="127.0.0.1", port=8080):
    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
        print(f"Discord HTTP API: http://{host}:{port}")
        await bot.start(token)
    finally:
        await runner.cleanup()
        await bot.close()
