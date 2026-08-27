from __future__ import annotations

import json
import logging
import os
import socket
import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def nacos_enabled() -> bool:
    return env_bool("NACOS_ENABLED", False)


def normalize_nacos_server_addr(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value:
        raise RuntimeError("NACOS_SERVER_ADDR is not configured")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    if not value.endswith("/nacos"):
        value = f"{value}/nacos"
    return value


def local_ip() -> str:
    configured = os.getenv("NACOS_REGISTER_IP", "").strip()
    if configured:
        return configured
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())
    finally:
        sock.close()


@dataclass(frozen=True)
class NacosInstance:
    ip: str
    port: int
    service_name: str
    metadata: dict[str, Any]

    @classmethod
    def from_host(cls, service_name: str, host: dict[str, Any]) -> "NacosInstance":
        metadata = host.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        return cls(ip=str(host["ip"]), port=int(host["port"]), service_name=service_name, metadata=dict(metadata))


class NacosClient:
    def __init__(
        self,
        server_addr: str | None = None,
        namespace_id: str | None = None,
        group_name: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.server_addr = normalize_nacos_server_addr(server_addr or os.getenv("NACOS_SERVER_ADDR", ""))
        self.namespace_id = namespace_id if namespace_id is not None else os.getenv("NACOS_NAMESPACE_ID", "")
        self.group_name = group_name or os.getenv("NACOS_GROUP_NAME", "DEFAULT_GROUP")
        self.cluster_name = os.getenv("NACOS_CLUSTER_NAME", "DEFAULT")
        self.timeout = timeout or float(os.getenv("NACOS_TIMEOUT", "5"))
        self._access_token: str | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        params = dict(kwargs.pop("params", {}) or {})
        if self.namespace_id:
            params.setdefault("namespaceId", self.namespace_id)
        if self._access_token:
            params.setdefault("accessToken", self._access_token)
        response = requests.request(method, f"{self.server_addr}{path}", params=params, timeout=self.timeout, **kwargs)
        if response.status_code in {401, 403} and os.getenv("NACOS_USERNAME"):
            self._login()
            params["accessToken"] = self._access_token
            response = requests.request(method, f"{self.server_addr}{path}", params=params, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response

    def _login(self) -> None:
        username = os.getenv("NACOS_USERNAME", "")
        password = os.getenv("NACOS_PASSWORD", "")
        if not username:
            return
        response = requests.post(
            f"{self.server_addr}/v1/auth/login",
            data={"username": username, "password": password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data.get("accessToken")

    def register_instance(
        self,
        service_name: str,
        ip: str,
        port: int,
        metadata: dict[str, Any] | None = None,
        ephemeral: bool | None = None,
    ) -> None:
        params = {
            "serviceName": service_name,
            "groupName": self.group_name,
            "clusterName": self.cluster_name,
            "ip": ip,
            "port": str(port),
            "weight": os.getenv("NACOS_WEIGHT", "1"),
            "enabled": "true",
            "healthy": "true",
            "ephemeral": str(env_bool("NACOS_EPHEMERAL", True) if ephemeral is None else ephemeral).lower(),
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        }
        self._request("POST", "/v1/ns/instance", params=params)

    def deregister_instance(self, service_name: str, ip: str, port: int, ephemeral: bool | None = None) -> None:
        params = {
            "serviceName": service_name,
            "groupName": self.group_name,
            "clusterName": self.cluster_name,
            "ip": ip,
            "port": str(port),
            "ephemeral": str(env_bool("NACOS_EPHEMERAL", True) if ephemeral is None else ephemeral).lower(),
        }
        self._request("DELETE", "/v1/ns/instance", params=params)

    def send_heartbeat(
        self,
        service_name: str,
        ip: str,
        port: int,
        metadata: dict[str, Any] | None = None,
        ephemeral: bool | None = None,
    ) -> None:
        is_ephemeral = env_bool("NACOS_EPHEMERAL", True) if ephemeral is None else ephemeral
        beat = {
            "serviceName": service_name,
            "ip": ip,
            "port": port,
            "cluster": self.cluster_name,
            "weight": float(os.getenv("NACOS_WEIGHT", "1")),
            "metadata": metadata or {},
            "scheduled": True,
        }
        params = {
            "serviceName": service_name,
            "groupName": self.group_name,
            "ephemeral": str(is_ephemeral).lower(),
            "beat": json.dumps(beat, ensure_ascii=False),
        }
        self._request("PUT", "/v1/ns/instance/beat", params=params)

    def list_instances(self, service_name: str, healthy_only: bool = True) -> list[NacosInstance]:
        params = {
            "serviceName": service_name,
            "groupName": self.group_name,
            "healthyOnly": str(healthy_only).lower(),
        }
        response = self._request("GET", "/v1/ns/instance/list", params=params)
        data = response.json()
        hosts = data.get("hosts") or []
        return [
            NacosInstance.from_host(service_name, host)
            for host in hosts
            if host.get("ip") and host.get("port") and host.get("enabled", True)
        ]

    def select_instance(self, service_name: str) -> NacosInstance:
        instances = self.list_instances(service_name, healthy_only=True)
        if not instances:
            raise RuntimeError(f"no healthy Nacos instance found for service {service_name!r}")
        for instance in instances:
            if not instance.ip.startswith("127.") and instance.ip != "localhost":
                return instance
        return instances[0]

    def get_config(self, data_id: str, group_name: str | None = None) -> str:
        params = {
            "dataId": data_id,
            "group": group_name or os.getenv("NACOS_CONFIG_GROUP", self.group_name),
        }
        response = self._request("GET", "/v1/cs/configs", params=params)
        return response.text

    def get_json_config(self, data_id: str, group_name: str | None = None) -> dict[str, Any]:
        text = self.get_config(data_id, group_name)
        try:
            data = json.loads(text)
        except Exception as exc:
            raise RuntimeError(f"Nacos config {data_id!r} is not valid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Nacos config {data_id!r} must be a JSON object")
        return data

    def listen_config(
        self,
        data_id: str,
        callback,
        group_name: str | None = None,
        interval_seconds: float | None = None,
    ) -> threading.Event:
        interval = max(1.0, interval_seconds or float(os.getenv("NACOS_CONFIG_POLL_INTERVAL_SECONDS", "15")))
        group = group_name or os.getenv("NACOS_CONFIG_GROUP", self.group_name)
        stopped = threading.Event()

        def _loop() -> None:
            last_digest: str | None = None
            while not stopped.wait(interval):
                try:
                    text = self.get_config(data_id, group)
                    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
                    if digest != last_digest:
                        last_digest = digest
                        callback(text)
                except Exception as exc:
                    logger.warning("failed to poll Nacos config %s/%s: %s", group, data_id, exc)

        thread = threading.Thread(target=_loop, name=f"nacos-config-{data_id}", daemon=True)
        thread.start()
        return stopped


class NacosServiceRegistrar:
    def __init__(self, service_name: str, port: int, metadata: dict[str, Any] | None = None) -> None:
        self.service_name = service_name
        self.port = port
        self.ip = local_ip()
        self.metadata = metadata or {}
        self.client = NacosClient()
        self.interval = max(1.0, float(os.getenv("NACOS_HEARTBEAT_INTERVAL_SECONDS", "5")))
        self.ephemeral = env_bool("NACOS_EPHEMERAL", True)
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.client.register_instance(self.service_name, self.ip, self.port, self.metadata, self.ephemeral)
        if self.ephemeral:
            self._thread = threading.Thread(target=self._heartbeat_loop, name=f"nacos-heartbeat-{self.service_name}", daemon=True)
            self._thread.start()
        logger.info("registered service %s to Nacos at %s:%s", self.service_name, self.ip, self.port)

    def stop(self) -> None:
        self._stopped.set()
        try:
            self.client.deregister_instance(self.service_name, self.ip, self.port, self.ephemeral)
        except Exception as exc:
            logger.warning("failed to deregister service %s from Nacos: %s", self.service_name, exc)

    def _heartbeat_loop(self) -> None:
        while not self._stopped.wait(self.interval):
            try:
                self.client.send_heartbeat(self.service_name, self.ip, self.port, self.metadata, self.ephemeral)
            except Exception as exc:
                logger.warning("failed to send Nacos heartbeat for %s: %s", self.service_name, exc)


def register_current_service(
    service_name_env: str,
    default_service_name: str,
    port_env: str,
    metadata: dict[str, Any],
    fallback_port_env: str | None = None,
) -> NacosServiceRegistrar | None:
    if not nacos_enabled():
        return None
    service_name = os.getenv(service_name_env, default_service_name).strip()
    if not service_name:
        logger.warning("Nacos enabled but %s is empty, skip registration", service_name_env)
        return None
    # start-local.ps1 may choose a free runtime port and write it into PARSE_PORT/RETRIEVE_PORT.
    # Prefer that runtime port; keep NACOS_*_REGISTER_PORT as an explicit deployment fallback.
    port_value = (os.getenv(fallback_port_env) if fallback_port_env else None) or os.getenv(port_env) or "0"
    port = int(str(port_value).strip() or "0")
    if port <= 0:
        logger.warning("Nacos enabled but %s is not configured, skip registration", port_env)
        return None
    registrar = NacosServiceRegistrar(service_name=service_name, port=port, metadata=metadata)
    try:
        registrar.start()
        return registrar
    except Exception as exc:
        logger.warning("failed to register %s to Nacos: %s", service_name, exc)
        return None


def resolve_service_base_url(service_name: str, context_path: str | None = None, scheme: str | None = None) -> str:
    client = NacosClient()
    instance = client.select_instance(service_name)
    path = context_path
    if path is None:
        path = (
            instance.metadata.get("contextPath")
            or instance.metadata.get("context_path")
            or instance.metadata.get("basePath")
            or instance.metadata.get("base_path")
            or ""
        )
    normalized_path = f"/{path.strip('/')}" if path else ""
    protocol = scheme or instance.metadata.get("scheme") or instance.metadata.get("protocol") or os.getenv("NACOS_DISCOVERY_SCHEME", "http")
    return f"{protocol}://{instance.ip}:{instance.port}{normalized_path}".rstrip("/")
