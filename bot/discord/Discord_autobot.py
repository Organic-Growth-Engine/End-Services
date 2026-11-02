import os
import asyncio
import disnake
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not TOKEN:
    raise ValueError("BOT_TOKEN is missing from .env")

if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID is missing from .env")

CHANNEL_ID = int(CHANNEL_ID)

client = disnake.Client(
    intents=disnake.Intents.default()
)


@client.event
async def on_ready():
    print(f"\nConnected as {client.user}")


async def publish():
    await client.wait_until_ready()

    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        print(f"Publishing to: {channel}")

    except disnake.NotFound:
        print("Error: Channel not found. Check CHANNEL_ID.")
        await client.close()
        return

    except disnake.Forbidden:
        print("Error: Bot cannot access this channel.")
        await client.close()
        return

    while not client.is_closed():
        print("\n--- Discord Publisher ---")
        print("1. Send text")
        print("2. Send image/video/audio")
        print("3. Exit")

        choice = await asyncio.to_thread(
            input, "\nChoose: "
        )

        try:
            if choice == "1":
                text = await asyncio.to_thread(
                    input, "Message: "
                )

                if not text.strip():
                    print("Message cannot be empty!")
                    continue

                await channel.send(content=text)
                print("Text published!")

            elif choice == "2":
                caption = await asyncio.to_thread(
                    input, "Caption (optional): "
                )

                path = await asyncio.to_thread(
                    input, "File path: "
                )

                path = path.strip().strip('"').strip()

                if not os.path.isfile(path):
                    print("Error: File not found!")
                    continue

                size_mb = os.path.getsize(path) / (1024 * 1024)
                print(f"File size: {size_mb:.2f} MB")

                media = disnake.File(path)

                try:
                    await channel.send(
                        content=caption or None,
                        file=media
                    )

                    print("Media published!")

                finally:
                    media.close()

            elif choice == "3":
                print("Disconnecting...")
                break

            else:
                print("Invalid option!")

        except disnake.Forbidden:
            print("Error: Bot lacks permission to publish.")

        except disnake.HTTPException as error:
            print("Discord API error:", error)

        except Exception as error:
            print("Error:", error)

    await client.close()


async def main():
    try:
        await asyncio.gather(
            client.start(TOKEN),
            publish()
        )

    finally:
        if not client.is_closed():
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())