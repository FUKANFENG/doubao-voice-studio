# Bundled voice client

`doubao_voice/` contains the four Python source files of the voice protocol client used by this project: common configuration, TTS, ASR, and package exports.

The service loads this bundled copy through `backend/config.py`, so a separate checkout or a Windows directory junction is not required. No account credentials, captured traffic, or runtime output are included. Configure your own session using the root `auth.example.json`.

This is an unofficial client for Doubao's web voice endpoints. Upstream protocol or login changes can require updates.
