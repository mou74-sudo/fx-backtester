"""Instagram Reels uploader via the Graph API.

Requires:
  * An Instagram Business or Creator account linked to a Facebook Page.
  * A Page access token with ``instagram_content_publish`` scope.
  * The video publicly hosted at a URL the Graph API can fetch (S3, CDN).

Two-step publish flow per Meta's docs:
  1. POST /{ig-user-id}/media with media_type=REELS, video_url, caption
     → returns a creation container id
  2. POST /{ig-user-id}/media_publish with creation_id once the container
     reports status_code=FINISHED

https://developers.facebook.com/docs/instagram-api/guides/content-publishing

This module only *calls* the Graph API. It does not scrape Instagram or
attempt to work around upload limits.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from reel_generator.models import UploadRequest

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v20.0"


@dataclass
class InstagramReelUploader:
    """Publishes a Reel. Network-only — there is no local ffmpeg step here.

    Parameters
    ----------
    ig_user_id: Instagram Business Account ID.
    access_token: Long-lived Page access token.
    session: requests.Session (injected so tests can pass a mock).
    poll_interval_s, max_poll_s: how long to wait for container processing.
    """

    ig_user_id: str
    access_token: str
    session: Any
    poll_interval_s: float = 4.0
    max_poll_s: float = 180.0

    @classmethod
    def from_env(cls, session: Any) -> InstagramReelUploader:
        ig_user_id = os.environ["IG_USER_ID"]
        token = os.environ["IG_ACCESS_TOKEN"]
        return cls(ig_user_id=ig_user_id, access_token=token, session=session)

    def publish(self, request: UploadRequest) -> dict:
        creation_id = self._create_container(request)
        self._wait_for_container(creation_id)
        return self._publish_container(creation_id)

    def _create_container(self, request: UploadRequest) -> str:
        url = f"{GRAPH_BASE}/{self.ig_user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": str(request.video_url),
            "caption": request.caption,
            "share_to_feed": str(request.share_to_feed).lower(),
            "access_token": self.access_token,
        }
        resp = self.session.post(url, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        creation_id = data.get("id")
        if not creation_id:
            raise RuntimeError(f"Graph API did not return a creation id: {data}")
        logger.info("Created IG media container %s", creation_id)
        return creation_id

    def _wait_for_container(self, creation_id: str) -> None:
        url = f"{GRAPH_BASE}/{creation_id}"
        deadline = time.monotonic() + self.max_poll_s
        while time.monotonic() < deadline:
            resp = self.session.get(
                url,
                params={"fields": "status_code", "access_token": self.access_token},
                timeout=15,
            )
            resp.raise_for_status()
            status = resp.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError(f"IG container {creation_id} failed to process")
            time.sleep(self.poll_interval_s)
        raise TimeoutError(f"IG container {creation_id} not ready after {self.max_poll_s}s")

    def _publish_container(self, creation_id: str) -> dict:
        url = f"{GRAPH_BASE}/{self.ig_user_id}/media_publish"
        resp = self.session.post(
            url,
            data={"creation_id": creation_id, "access_token": self.access_token},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
