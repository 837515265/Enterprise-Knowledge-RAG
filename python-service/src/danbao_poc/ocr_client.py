from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


def call_paddle_ocr_predict(predict_url: str, file_name: str, file_bytes: bytes, timeout: int = 600) -> dict[str, Any]:
    if not predict_url:
        raise RuntimeError(
            "PADDLE_OCR_PREDICT_URL is not configured. "
            "Set it to your PaddleOCR ETL4LM-compatible endpoint, for example http://paddleocr-vl-api:8011/v1/etl4llm/predict"
        )
    payload = {
        "filename": file_name,
        "b64_data": [base64.b64encode(file_bytes).decode("ascii")],
        "mode": "partition",
        "force_ocr": False,
    }
    response = requests.post(predict_url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if int(data.get("status_code", 200)) >= 400:
        raise RuntimeError(f"OCR service returned error: {data}")
    return data


def call_ocr_web_v2(api_url: str, file_name: str, file_bytes: bytes, timeout: int = 600) -> dict[str, Any]:
    if not api_url:
        raise RuntimeError(
            "PADDLE_OCR_WEB_URL is not configured. "
            "Set it to your ocr-web-v2 endpoint, for example http://host.docker.internal:8118/api/ocr"
        )
    parsed = urlparse(api_url)
    if not parsed.path or parsed.path == "/":
        api_url = api_url.rstrip("/") + "/api/ocr"
    suffix = Path(file_name or "upload.pdf").suffix.lower()
    content_type = "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    safe_name = "upload" + suffix
    try:
        request_timeout = int(os.getenv("PADDLE_OCR_WEB_TIMEOUT", os.getenv("OCR_WEB_TIMEOUT", str(timeout))))
    except Exception:
        request_timeout = timeout
    response = requests.post(
        api_url,
        params={"return_raw": "true", "return_page_map": "true", "return_seals": "true"},
        files={"file": (safe_name, file_bytes, content_type)},
        timeout=request_timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success", False):
        raise RuntimeError(f"ocr-web-v2 returned error: {data}")
    if "raw_layout" not in data:
        raise RuntimeError("ocr-web-v2 response does not contain raw_layout. Call with return_raw=true.")
    return data


def _mineru_proxy_enabled() -> bool:
    return os.getenv("LLM_PROXY_ENABLED", "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_mineru_proxy_url() -> str:
    from .openai_compat import _resolve_inner_proxy_url
    return _resolve_inner_proxy_url()


def _call_mineru_via_proxy(api_url: str, file_name: str, file_bytes: bytes, timeout: int, *, file_id: str = "") -> dict[str, Any]:
    """Route MinerU parse through common-inner-proxy."""
    proxy_url = _resolve_mineru_proxy_url()
    endpoint = f"{proxy_url}/proxy/inner/request"

    suffix = Path(file_name or "upload.pdf").suffix.lower()
    safe_name = "upload" + suffix

    data = {
        "files": file_id or "placeholder",
        "lang_list": os.getenv("MINERU_LANG_LIST", "ch"),
        "backend": os.getenv("MINERU_BACKEND", "vlm-auto-engine"),
        "parse_method": os.getenv("MINERU_PARSE_METHOD", "auto"),
        "formula_enable": os.getenv("MINERU_FORMULA_ENABLE", "true").lower(),
        "table_enable": os.getenv("MINERU_TABLE_ENABLE", "true").lower(),
        "image_analysis": os.getenv("MINERU_IMAGE_ANALYSIS", "true").lower(),
        "return_md": "true",
        "return_middle_json": os.getenv("MINERU_RETURN_MIDDLE_JSON", "true").lower(),
        "return_content_list": os.getenv("MINERU_RETURN_CONTENT_LIST", "false").lower(),
        "return_images": os.getenv("MINERU_RETURN_IMAGES", "false").lower(),
        "response_format_zip": "false",
        "file_name": safe_name,
    }

    envelope = {
        "thirdAppId": "MINERU",
        "thirdInterfaceId": "mineru-parse",
        "applyAppId": os.getenv("LLM_PROXY_APPLY_APP_ID", "APP_KNOWLEDGE_SERVICE"),
        "thirdUrl": "/file_parse",
        "methodType": "POST",
        "data": data,
        "fileKeys": [{"key": "files", "type": 0}],
    }

    response = requests.post(endpoint, json=envelope, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    # Unwrap proxy envelope
    code = result.get("resp_code") if "resp_code" in result else result.get("code")
    if code not in (0, 200, None):
        msg = result.get("resp_msg") or result.get("msg") or result.get("message") or "unknown"
        raise RuntimeError(f"MinerU proxy error: code={code}, msg={msg}")

    datas = result.get("datas") if "datas" in result else result.get("data") or result.get("result")
    if datas is None:
        raise RuntimeError(f"MinerU proxy returned empty datas")

    if isinstance(datas, str):
        try:
            datas = json.loads(datas)
        except Exception:
            raise RuntimeError(f"MinerU proxy datas is not valid JSON: {datas[:500]}")

    if isinstance(datas, dict):
        status = str(datas.get("status") or "").lower()
        if status and status not in {"completed", "success"}:
            raise RuntimeError(f"MinerU returned non-completed status: {datas}")
        results = datas.get("results")
        if not isinstance(results, dict) or not results:
            raise RuntimeError(f"MinerU response does not contain results: {datas}")
        return datas

    raise RuntimeError(f"MinerU unexpected datas type: {type(datas).__name__}")


def call_mineru_parse(api_url: str, file_name: str, file_bytes: bytes, timeout: int = 900, *, file_id: str = "") -> dict[str, Any]:
    if _mineru_proxy_enabled():
        return _call_mineru_via_proxy(api_url, file_name, file_bytes, int(os.getenv("MINERU_TIMEOUT", str(timeout))), file_id=file_id)

    if not api_url:
        raise RuntimeError("MINERU_BASE_URL must be configured when OCR_BACKEND=mineru")
    parsed = urlparse(api_url)
    if not parsed.path or parsed.path == "/":
        api_url = api_url.rstrip("/") + "/file_parse"
    suffix = Path(file_name or "upload.pdf").suffix.lower()
    content_type = "application/pdf" if suffix == ".pdf" else "application/octet-stream"
    safe_name = "upload" + suffix
    data = {
        "lang_list": os.getenv("MINERU_LANG_LIST", "ch"),
        "backend": os.getenv("MINERU_BACKEND", "vlm-auto-engine"),
        "parse_method": os.getenv("MINERU_PARSE_METHOD", "auto"),
        "formula_enable": os.getenv("MINERU_FORMULA_ENABLE", "true").lower(),
        "table_enable": os.getenv("MINERU_TABLE_ENABLE", "true").lower(),
        "image_analysis": os.getenv("MINERU_IMAGE_ANALYSIS", "true").lower(),
        "return_md": "true",
        "return_middle_json": os.getenv("MINERU_RETURN_MIDDLE_JSON", "true").lower(),
        "return_content_list": os.getenv("MINERU_RETURN_CONTENT_LIST", "false").lower(),
        "return_images": os.getenv("MINERU_RETURN_IMAGES", "false").lower(),
        "response_format_zip": "false",
    }
    response = requests.post(
        api_url,
        files={"files": (safe_name, file_bytes, content_type)},
        data=data,
        timeout=int(os.getenv("MINERU_TIMEOUT", str(timeout))),
    )
    response.raise_for_status()
    result = response.json()
    status = str(result.get("status") or "").lower()
    if status and status not in {"completed", "success"}:
        raise RuntimeError(f"MinerU returned non-completed status: {result}")
    results = result.get("results")
    if not isinstance(results, dict) or not results:
        raise RuntimeError(f"MinerU response does not contain results: {result}")
    return result


def call_qianfan_vlm_ocr(
    *,
    base_url: str,
    model: str,
    api_key: str,
    image_bytes: bytes,
    image_mime_type: str = "image/png",
    prompt: str | None = None,
    timeout: int = 600,
    append_think: bool | None = None,
) -> dict[str, Any]:
    if not base_url or not model:
        raise RuntimeError("QIANFAN_OCR_BASE_URL and QIANFAN_OCR_MODEL must be configured")
    prompt = prompt or (
        "你是一个文档OCR与版面重建模型。请忠实提取这页文档的全部可见文字，并重建为结构清晰的 Markdown。\n"
        "要求：\n"
        "1. 不要总结，不要改写，不要补充不存在的内容。\n"
        "2. 保留标题层级、段落顺序、编号层级。\n"
        "3. 表格请输出为 Markdown 表格。\n"
        "4. 印章、签名、批注、页眉页脚请单独标注。\n"
        "5. 无法识别的少量字符可用 [?] 标记，但不要整段省略。\n"
        "6. 只输出最终 Markdown，不要输出解释。"
    )
    if append_think is None:
        append_think = os.getenv("QIANFAN_OCR_APPEND_THINK", "true").lower() in {"1", "true", "yes", "on"}
    if append_think and not prompt.rstrip().endswith("<think>"):
        prompt = f"{prompt}\n<think>"

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    normalized_base_url = base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key or 'EMPTY'}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{image_mime_type};base64,{image_b64}"},
                    },
                ],
            }
        ],
    }
    response = requests.post(f"{normalized_base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"qianfan vlm ocr returned invalid response: {data}") from exc
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                text_parts.append(item)
        markdown = "\n".join(part for part in text_parts if part).strip()
    else:
        markdown = str(content or "").strip()
    if not markdown:
        raise RuntimeError(f"qianfan vlm ocr returned empty markdown: {data}")
    return {"raw_response": data, "markdown": markdown}
