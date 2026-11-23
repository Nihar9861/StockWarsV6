"""Single-process entrypoint for Railway: FastAPI (Mini App + API) and the bot together. Keep replicas = 1."""
import asyncio, os
import uvicorn
from .bot.main import main as bot_main


async def run():
    server = uvicorn.Server(uvicorn.Config("app.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info"))
    tasks = [asyncio.create_task(server.serve()), asyncio.create_task(bot_main())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending: t.cancel()
    for t in done: t.result()


if __name__ == "__main__":
    asyncio.run(run())
