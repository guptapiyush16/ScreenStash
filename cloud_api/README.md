# ScreenStash Cloud API

This Render Web Service provides optional Gemini extraction for the desktop app.
It receives OCR text and a filename, never the screenshot image, and does not
write either to the quota database or application logs.

## Deploy on Render

1. Push this repository and create a **Blueprint** from `cloud_api/render.yaml`.
2. In the service's **Environment** settings, add `GEMINI_API_KEY` as a secret.
   Do not put it in this repository, the Render build command, or the desktop app.
3. Deploy and record the HTTPS service URL, for example
   `https://screenstash-cloud-api.onrender.com`.
4. Configure that exact URL in the desktop release build before enabling Cloud AI.

The API enforces 50 successful extractions per calendar month per installation.
This is a fair-use quota, not account security: a user can reset a local
installation identifier. Add real sign-in and verify the user token at this API
before using it for billing or a paid plan.
