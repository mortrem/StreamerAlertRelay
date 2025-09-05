# test.py
#
# A minimal script to spin up Playwright, open one chat stream using
# your parser’s get_chat_url, hook into the raw WebSocket frames, and
# print both the raw payload and your parser’s parse_frame() output.
#
# Usage:
#   python test.py <parser_module> <username_or_url>
# Example:
#   python test.py youtube_parse https://www.youtube.com/watch?v=XYZ123

import sys
import asyncio
import os
from playwright.async_api import async_playwright
from driver import ensure_chromium_installed

async def test_stream(parser, source_id):
    # Make sure Playwright browsers are installed in your local playwright_home
    ensure_chromium_installed()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page    = await context.new_page()
        cdp     = await context.new_cdp_session(page)
        await cdp.send("Network.enable")

        # Handler prints raw frame, raw payload, and parser output
        def on_ws_frame(frame):
            print("=== RAW CDP FRAME ===")
            print(frame, "\n")
            payload = frame["response"]["payloadData"]
            print("=== WS PAYLOAD ===")
            print(payload, "\n")
            result = parser.parse_frame(payload)
            print("=== PARSER RESULT ===")
            print(result, "\n\n")

        cdp.on("Network.webSocketFrameReceived", on_ws_frame)

        chat_url = parser.get_chat_url(source_id)
        print(f"→ Navigating to {chat_url}\n")
        await page.goto(chat_url)

        print("Listening for WebSocket frames. Press Ctrl+C to exit.\n")
        try:
            # keep running until interrupted
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nInterrupted by user, closing…")
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test.py <parser_module> <username_or_url>")
        sys.exit(1)

    module_name, source_id = sys.argv[1], sys.argv[2]
    # Dynamically import the parser module
    spec = __import__(module_name)
    parser = spec

    asyncio.run(test_stream(parser, source_id))