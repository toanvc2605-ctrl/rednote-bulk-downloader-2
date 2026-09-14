# RedNote Bulk Downloader — Render

Render-ready FastAPI + Playwright service. Chromium is installed from Debian packages instead of downloading a ~180 MB Playwright browser during the Render build, which avoids the build failure seen on Render.

## Deploy

Create a Render Web Service from this repository. Runtime: Docker. No custom build/start command is required because the Dockerfile contains the startup command.

The service listens on Render's `$PORT` and exposes `/health`.

## Notes

- Works with publicly accessible RedNote/Xiaohongshu profile pages.
- Does not bypass CAPTCHA, private accounts, or access controls.
- RedNote may change its page/API structure; the scanner includes DOM fallback for post links.
