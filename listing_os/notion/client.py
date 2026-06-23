from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib import request

from .ids import normalize_notion_id


NOTION_VERSION = "2026-03-11"
NOTION_API_BASE = "https://api.notion.com/v1"


class NotionClient:
    def __init__(self, token: str, notion_version: str = NOTION_VERSION, timeout: int = 60) -> None:
        self.token = token
        self.notion_version = notion_version
        self.timeout = timeout

    def create_database(self, payload: dict[str, Any]) -> dict[str, Any]:
        _normalize_parent_page_id(payload)
        return self._request("POST", "/databases", payload)

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self._request("GET", f"/databases/{database_id}", None)

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self._request("GET", f"/data_sources/{data_source_id}", None)

    def update_database(self, database_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/databases/{database_id}", payload)

    def list_block_children(self, block_id: str, page_size: int = 100, start_cursor: str | None = None) -> dict[str, Any]:
        block_id = normalize_notion_id(block_id)
        path = f"/blocks/{block_id}/children?page_size={page_size}"
        if start_cursor:
            path += f"&start_cursor={start_cursor}"
        return self._request("GET", path, None)

    def update_data_source(self, data_source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/data_sources/{data_source_id}", payload)

    def query_data_source(self, data_source_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", f"/data_sources/{data_source_id}/query", payload or {})

    def archive_block(self, block_id: str) -> dict[str, Any]:
        block_id = normalize_notion_id(block_id)
        return self._request("PATCH", f"/blocks/{block_id}", {"in_trash": True})

    def trash_database(self, database_id: str) -> dict[str, Any]:
        return self.update_database(database_id, {"in_trash": True})

    def trash_page(self, page_id: str) -> dict[str, Any]:
        page_id = normalize_notion_id(page_id)
        return self._request("PATCH", f"/pages/{page_id}", {"in_trash": True})

    def create_page(self, data_source_id: str, properties: dict[str, Any], children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": properties,
        }
        if children:
            payload["children"] = children
        return self._request("POST", "/pages", payload)

    def create_file_upload(self, *, filename: str | None = None, content_type: str | None = None, mode: str = "single_part") -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": mode}
        if filename:
            payload["filename"] = filename
        if content_type:
            payload["content_type"] = content_type
        return self._request("POST", "/file_uploads", payload)

    def send_file_upload(self, file_upload_id: str, file_path: str | Path, *, content_type: str | None = None) -> dict[str, Any]:
        path = Path(file_path)
        content_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        boundary = f"----notion-file-upload-{uuid.uuid4().hex}"
        file_bytes = path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                f"\r\n--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        return self._raw_request(
            "POST",
            f"/file_uploads/{file_upload_id}/send",
            body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    def complete_file_upload(self, file_upload_id: str) -> dict[str, Any]:
        return self._request("POST", f"/file_uploads/{file_upload_id}/complete", {})

    def upload_file(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if path.stat().st_size > 20 * 1024 * 1024:
            raise RuntimeError(f"Notion direct upload supports files up to 20MB: {path}")
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        upload = self.create_file_upload(filename=path.name, content_type=content_type)
        upload_id = upload.get("id", "")
        if not upload_id:
            raise RuntimeError(f"Notion file upload did not return an id for {path}")
        sent = self.send_file_upload(upload_id, path, content_type=content_type)
        if sent.get("status") not in {"uploaded", None}:
            raise RuntimeError(f"Notion file upload failed for {path}: {sent}")
        return upload_id

    def create_child_page(self, parent_page_id: str, title: str, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        parent_page_id = normalize_notion_id(parent_page_id)
        payload: dict[str, Any] = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": title}}],
                }
            },
        }
        if children:
            payload["children"] = children
        return self._request("POST", "/pages", payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        return self._raw_request(method, path, body, {"Content-Type": "application/json"})

    def _raw_request(self, method: str, path: str, body: bytes | None, extra_headers: dict[str, str]) -> dict[str, Any]:
        req = request.Request(
            NOTION_API_BASE + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.notion_version,
                **extra_headers,
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Notion API {method} {path} failed with HTTP {error.code}: {detail}") from error


def _normalize_parent_page_id(payload: dict[str, Any]) -> None:
    parent = payload.get("parent")
    if isinstance(parent, dict) and parent.get("type") == "page_id" and isinstance(parent.get("page_id"), str):
        parent["page_id"] = normalize_notion_id(parent["page_id"])
