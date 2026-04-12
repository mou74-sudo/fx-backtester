from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from reel_generator.models import UploadRequest
from reel_generator.upload.instagram import InstagramReelUploader


@dataclass
class FakeResponse:
    _json: Any
    status_code: int = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, url, data=None, timeout=None):  # noqa: ARG002
        self.calls.append(("POST", url, data or {}))
        return self._responses.pop(0)

    def get(self, url, params=None, timeout=None):  # noqa: ARG002
        self.calls.append(("GET", url, params or {}))
        return self._responses.pop(0)


def test_publish_happy_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "reel_generator.upload.instagram.time.sleep", lambda _s: None
    )
    session = FakeSession(
        [
            FakeResponse({"id": "container-123"}),  # POST /media
            FakeResponse({"status_code": "IN_PROGRESS"}),  # GET status
            FakeResponse({"status_code": "FINISHED"}),
            FakeResponse({"id": "published-456"}),  # POST /media_publish
        ]
    )
    uploader = InstagramReelUploader(
        ig_user_id="IG1", access_token="TOK", session=session, poll_interval_s=0.0
    )
    request = UploadRequest(
        video_url="https://cdn.example.com/reel.mp4",
        caption="Luteal-phase lifts. Made with AI. #AI",
    )
    result = uploader.publish(request)
    assert result == {"id": "published-456"}
    # First call was the container creation with media_type=REELS
    first = session.calls[0]
    assert first[0] == "POST"
    assert first[2]["media_type"] == "REELS"
    assert first[2]["caption"] == request.caption


def test_publish_raises_on_container_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "reel_generator.upload.instagram.time.sleep", lambda _s: None
    )
    session = FakeSession(
        [
            FakeResponse({"id": "container-err"}),
            FakeResponse({"status_code": "ERROR"}),
        ]
    )
    uploader = InstagramReelUploader(
        ig_user_id="IG1", access_token="TOK", session=session, poll_interval_s=0.0
    )
    with pytest.raises(RuntimeError):
        uploader.publish(
            UploadRequest(
                video_url="https://cdn.example.com/reel.mp4",
                caption="test #AI",
            )
        )
