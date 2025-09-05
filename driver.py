# driver.py

import asyncio
import os
import subprocess
from threading import Thread
from queue import Queue
from playwright.async_api import async_playwright

event_queue    = Queue()
_driver_loop   = None
_driver_thread = None
_driver_task   = None

def start_driver(sources):
    stop_driver()

    def _thread_target():
        global _driver_loop, _driver_task
        _driver_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_driver_loop)

        # install exception handler to suppress “Event loop is closed” noise
        def _handle_loop_exc(loop, context):
            # ignore errors about closed loop or broken pipe
            msg = context.get("message", "")
            if "Event loop is closed" in msg or "broken pipe" in msg:
                return
            loop.default_exception_handler(context)

        _driver_loop.set_exception_handler(_handle_loop_exc)

        _driver_task = _driver_loop.create_task(run_driver(sources))
        _driver_loop.run_forever()

    global _driver_thread
    _driver_thread = Thread(target=_thread_target, daemon=True)
    _driver_thread.start()


def stop_driver():
    """
    Shutdown the playwright driver cleanly:
     1) cancel the main run_driver task
     2) cancel any remaining tasks (e.g. Connection.run)
     3) await them all
     4) stop the loop
    """
    global _driver_loop, _driver_thread, _driver_task

    if _driver_loop and _driver_loop.is_running():
        async def _shutdown():
            # 1) cancel the primary driver task
            if _driver_task:
                _driver_task.cancel()
                try:
                    await _driver_task
                except asyncio.CancelledError:
                    pass

            # 2) cancel all other pending tasks
            current = asyncio.current_task()
            tasks = [
                t for t in asyncio.all_tasks()
                if t is not current and not t.done()
            ]
            for t in tasks:
                t.cancel()

            # 3) wait for them to finish/cancel
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # 4) stop the loop
            _driver_loop.stop()

        # schedule shutdown on the driver loop
        fut = asyncio.run_coroutine_threadsafe(_shutdown(), _driver_loop)
        try:
            fut.result(timeout=10)
        except Exception:
            pass

    # join the thread so it fully exits
    if _driver_thread and _driver_thread.is_alive():
        _driver_thread.join(timeout=5)

    _driver_loop   = None
    _driver_thread = None
    _driver_task   = None


def ensure_chromium_installed():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.abspath("playwright_home")
    chromium_path = os.path.join(
        os.environ["PLAYWRIGHT_BROWSERS_PATH"],
        "chromium-1187", "chrome-win", "chrome.exe"
    )
    if not os.path.exists(chromium_path):
        try:
            subprocess.run(
                ["playwright", "install", "chromium"],
                check=True, env=os.environ,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except:
            pass


async def run_driver(sources):
    ensure_chromium_installed()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-gpu",
                "--mute-audio",
                "--window-position=-32000,-32000",
                "--window-size=800,600",
            ]
        )

        contexts = []
        for source in sources:
            parser    = source["parser"]
            source_id = source["username"]
            url       = parser.get_chat_url(source_id)

            ctx = await browser.new_context()
            contexts.append(ctx)

            await ctx.route("**/*", lambda r, req: (
                r.abort() if req.resource_type in ("image", "media", "font")
                else r.continue_()
            ))

            page = await ctx.new_page()
            cdp  = await ctx.new_cdp_session(page)
            await cdp.send("Network.enable")

            if hasattr(parser, "attach_listeners"):
                parser.attach_listeners(page, cdp, event_queue, source_id)
            else:
                def _ws_handler(frame, pr=parser, sid=source_id):
                    payload = frame["response"]["payloadData"]
                    res     = pr.parse_frame(payload)
                    if res:
                        ek, fmt = res
                        event_queue.put((
                            pr.__name__, sid, ek,
                            fmt["trigger"], fmt["customData"]
                        ))
                cdp.on("Network.webSocketFrameReceived", _ws_handler)

            await page.goto(url)

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            # cancellation triggers cleanup below
            pass
        finally:
            for ctx in contexts:
                await ctx.close()
            await browser.close()