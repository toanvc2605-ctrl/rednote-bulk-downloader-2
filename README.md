# RedNote Bulk Downloader — Render Ready

Web app for scanning a **public RedNote/Xiaohongshu profile**, finding public video posts, resolving the media URL in a browser session, and packaging selected videos into a ZIP.

> Use only for content you are authorized to download. The app does not bypass CAPTCHA, private accounts, paywalls, or access controls.

## Deploy on Render

This project is prepared as a Docker Web Service because Playwright/Chromium needs OS-level dependencies. Render supports Docker services directly.

1. Put this folder in a GitHub repository.
2. In Render, choose **New → Web Service** and connect the repository.
3. Select **Docker** as the runtime. Render will use the root `Dockerfile`.
4. Choose a plan. The included `render.yaml` is configured for the Free plan.
5. Deploy.

The container binds to `0.0.0.0` and uses Render's `$PORT` environment variable (defaulting to 10000).

## Local run

```bash
pip install -r requirements.txt
playwright install chromium
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Notes

- Render Free services can spin down after inactivity.
- Temporary downloaded files live in the container filesystem and are not intended as permanent storage.
- RedNote can change its frontend/API behavior, so profile scanning may need maintenance over time.
- A user-supplied Cookie string is used only for the current request and is not persisted by the app.
