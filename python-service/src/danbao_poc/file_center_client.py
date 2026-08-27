from __future__ import annotations

import base64
import re
import mimetypes
import os
from pathlib import Path
from typing import Any

from danbao_poc.nacos_client import nacos_enabled, resolve_service_base_url
from danbao_poc.service_client import ServiceClient, configured_service_name
from danbao_poc.settings import env_int, env_str


def _format_file_path(template: str, file_id: int | str) -> str:
    value = str(file_id)
    if "{id}" in template:
        return template.replace("{id}", value)
    if "{file_id}" in template:
        return template.replace("{file_id}", value)
    if "{fileId}" in template:
        return template.replace("{fileId}", value)
    if re.search(r"/$", template):
        return f"{template}{value}"
    return template


def _resolve_file_center_base_url(base_url: str | None = None) -> str:
    raw = (base_url or os.getenv("FILE_CENTER_BASE_URL", "")).strip().rstrip("/")
    if raw:
        return raw
    service_name = (os.getenv("FILE_CENTER_SERVICE_NAME") or os.getenv("NACOS_FILE_CENTER_SERVICE_NAME") or "").strip()
    if nacos_enabled() and service_name:
        return resolve_service_base_url(
            service_name,
            context_path=os.getenv("FILE_CENTER_CONTEXT_PATH", "").strip() or None,
            scheme=os.getenv("FILE_CENTER_SCHEME", "").strip() or None,
        )
    raise RuntimeError("FILE_CENTER_BASE_URL or FILE_CENTER_SERVICE_NAME is not configured")


class FileCenterClient:
    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        self.base_url = _resolve_file_center_base_url(base_url)
        self.timeout = timeout or env_int("FILE_CENTER_TIMEOUT", 120)
        self.client = ServiceClient(base_url=self.base_url, timeout=self.timeout, retries=env_int("FILE_CENTER_RETRIES", 2))

    @classmethod
    def from_config(cls) -> "FileCenterClient":
        base_url = env_str("FILE_CENTER_BASE_URL")
        if base_url:
            return cls(base_url=base_url)
        service_name = configured_service_name("FILE_CENTER_SERVICE_NAME", "NACOS_FILE_CENTER_SERVICE_NAME")
        if not service_name:
            return cls()
        context_path = env_str("FILE_CENTER_CONTEXT_PATH") or None
        scheme = env_str("FILE_CENTER_SCHEME") or None
        instance_base_url = resolve_service_base_url(service_name, context_path=context_path, scheme=scheme) if nacos_enabled() else ""
        return cls(base_url=instance_base_url or None)

    def get_files_info(self, file_ids: list[int] | list[str], request_id: str | None = None) -> list[dict[str, Any]]:
        data = self.client.json(
            "POST",
            env_str("FILE_CENTER_INFO_PATH", "/files/ids"),
            json={"ids": [str(item) for item in file_ids]},
            request_id=request_id,
        )
        if isinstance(data, list):
            return data
        return data.get("data") or data.get("datas") or []

    def get_file_info(self, file_id: int | str, request_id: str | None = None) -> dict[str, Any]:
        infos = self.get_files_info([file_id], request_id=request_id)
        if not infos:
            raise RuntimeError(f"file center did not return file info for file_id={file_id}")
        return infos[0]

    def download_file(self, file_id: int | str, request_id: str | None = None) -> tuple[str, bytes]:
        method = env_str("FILE_CENTER_DOWNLOAD_METHOD", "GET").upper()
        path = _format_file_path(env_str("FILE_CENTER_DOWNLOAD_PATH", "/files/{id}"), file_id)
        if method == "GET":
            response = self.client.request("GET", path, request_id=request_id, stream=False)
            file_name = self._download_file_name(file_id, response.headers)
            return file_name, response.content

        data = self.client.json(
            method,
            path,
            json={"fileId": str(file_id), "id": str(file_id)},
            request_id=request_id,
        )
        biz = data.get("data") or data.get("datas") or data if isinstance(data, dict) else {}
        file_name = biz.get("fileName") or biz.get("name") or f"{file_id}.bin"
        file_content = biz.get("fileContent") or biz.get("content")
        if not file_content:
            raise RuntimeError(f"file center response missing fileContent for file_id={file_id}")
        return file_name, base64.b64decode(file_content)

    @staticmethod
    def _download_file_name(file_id: int | str, headers: Any) -> str:
        content_disposition = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
        match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.IGNORECASE)
        if match:
            from urllib.parse import unquote

            return unquote(match.group(1).strip().strip('"'))
        match = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return f"{file_id}.bin"

    def download_to_path(self, file_id: int | str, target_path: str | Path, request_id: str | None = None) -> dict[str, Any]:
        file_name, file_bytes = self.download_file(file_id, request_id=request_id)
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_bytes)
        return {
            "file_name": file_name,
            "size": len(file_bytes),
            "mime_type": mimetypes.guess_type(file_name)[0] or "application/octet-stream",
            "path": str(target),
        }

    def upload_file(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        upload_path = env_str("FILE_CENTER_UPLOAD_PATH", "/files/upload")
        mode = env_str("FILE_CENTER_UPLOAD_MODE", "multipart").lower()
        if mode == "base64":
            data = self.client.json(
                "POST",
                upload_path,
                json={
                    "fileName": file_name,
                    "fileContent": base64.b64encode(file_bytes).decode("ascii"),
                    "metadata": metadata or {},
                },
                request_id=request_id,
            )
        else:
            response = self.client.request(
                "POST",
                upload_path,
                files={"file": (file_name, file_bytes, mimetypes.guess_type(file_name)[0] or "application/octet-stream")},
                data={key: str(value) for key, value in (metadata or {}).items()},
                request_id=request_id,
            )
            data = response.json()
        if isinstance(data, dict):
            return data.get("data") or data.get("datas") or data
        return {"data": data}

    def upload_path(
        self,
        path: str | Path,
        *,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        return self.upload_file(file_name=source.name, file_bytes=source.read_bytes(), request_id=request_id, metadata=metadata)
