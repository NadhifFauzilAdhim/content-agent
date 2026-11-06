"""Image adapters: OpenAI Images, Gemini (Imagen), and a Pillow mock renderer."""

from __future__ import annotations

import base64
import hashlib
import io
import time

from app.adapters.http import default_client, raise_for_status, with_retries
from app.ports.interfaces import GeneratedImage, ImageProvider, ProviderError, Usage

ASPECT_TO_SIZE = {
    "16:9": (1792, 1024),
    "9:16": (1024, 1792),
    "1:1": (1024, 1024),
    "4:3": (1024, 768),
    "3:4": (768, 1024),
}

#: Size strings the OpenAI Images API accepts; anything else must be sent as "auto".
_OPENAI_SIZES = {"256x256", "512x512", "1024x1024", "1536x1024", "1024x1536", "1792x1024", "1024x1792"}

#: Palette each response body can carry the image in.
_URL_KEYS = ("url", "b64_json", "image_url")


def _aspect_from_size(width: int, height: int, fallback: str) -> str:
    """Recover the aspect ratio from real pixels (providers may ignore the requested size)."""
    if not width or not height:
        return fallback
    ratio = width / height
    for name, (w, h) in ASPECT_TO_SIZE.items():
        if abs(ratio - w / h) < 0.02:
            return name
    return f"{width}x{height}"


def _image_dimensions(data: bytes) -> tuple[int, int]:
    """Pixel size from the image header (PNG/GIF/JPEG/WebP) without decoding the pixels."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001 - unknown formats fall back to the requested size
        return 0, 0


class _ImageGenHTTP:
    """Shared POST /images/generations client used by the OpenAI-style adapters."""

    name = "images"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")

    async def _fetch(self, entry: dict, timeout_s: float) -> tuple[bytes, str]:
        """Extract image bytes from one ``data[]`` entry (base64 inline or a temporary URL)."""
        b64 = entry.get("b64_json") or entry.get("image_base64")
        if isinstance(b64, str) and b64:
            if b64.startswith("data:"):  # data URI: strip the prefix
                b64 = b64.split(",", 1)[-1]
            return base64.b64decode(b64), "image/png"
        url = entry.get("url") or entry.get("image_url")
        if isinstance(url, dict):  # {"image_url": {"url": "..."}}
            url = url.get("url")
        if url:
            async with default_client(timeout_s) as client:
                img = await client.get(url)
            raise_for_status(img, self.name)
            mime = (img.headers.get("content-type") or "image/png").split(";")[0]
            return img.content, mime
        raise ProviderError(f"{self.name} response contained no image data")


class OpenAIImage(_ImageGenHTTP):
    """OpenAI Images API and any compatible endpoint with a custom model id.

    ``base_url`` points at the API root (``.../v1``), ``model`` may be any id the endpoint serves
    (for example ``ag/gemini-3.1-flash-image`` on a gateway). Optional request knobs are read from
    the provider's stored ``extra_config`` so operators can tune them without a code change:

    ``quality`` · ``background`` · ``image_detail`` · ``output_format`` · ``size``

    Every knob defaults to ``auto`` and is only sent when set, which keeps the request valid for
    strict OpenAI servers while still working on gateways that accept the extra fields.
    """

    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        *,
        options: dict[str, str] | None = None,
        label: str = "OpenAI Images",
    ) -> None:
        super().__init__(api_key, base_url)
        self._options = {k: v for k, v in (options or {}).items() if v not in (None, "")}
        self._label = label

    def _size_for(self, aspect_ratio: str) -> str:
        """Honour an explicit size, otherwise map the aspect ratio; unknown ratios use "auto"."""
        configured = self._options.get("size")
        if configured:
            return configured
        w, h = ASPECT_TO_SIZE.get(aspect_ratio, (0, 0))
        candidate = f"{w}x{h}"
        return candidate if candidate in _OPENAI_SIZES else "auto"

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        aspect_ratio: str = "16:9",
        model: str | None = None,
        reference_image: bytes | None = None,
        seed: int | None = None,
        timeout_s: float = 180.0,
    ) -> GeneratedImage:
        started = time.perf_counter()
        size = self._size_for(aspect_ratio)
        payload: dict[str, object] = {
            "model": model or "gpt-image-1",
            "prompt": prompt if not negative_prompt else f"{prompt}\n\nAvoid: {negative_prompt}",
            "n": 1,
            "size": size,
        }
        for key in ("quality", "background", "image_detail", "output_format"):
            value = self._options.get(key)
            if value:
                payload[key] = value
        if reference_image:
            payload["image"] = "data:image/png;base64," + base64.b64encode(reference_image).decode()

        async def call() -> GeneratedImage:
            async with default_client(timeout_s) as client:
                resp = await client.post(
                    f"{self._base}/images/generations",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=payload,
                )
            raise_for_status(resp, self._label)
            entries = (resp.json() or {}).get("data") or []
            if not entries:
                raise ProviderError(f"{self._label} returned no images")
            data, mime = await self._fetch(entries[0], timeout_s)
            width, height = _image_dimensions(data)
            if not width:  # header unreadable: fall back to the requested size
                width, height = ASPECT_TO_SIZE.get(aspect_ratio, (0, 0))
            return GeneratedImage(
                data=data,
                mime=mime,
                width=width,
                height=height,
                usage=Usage(
                    provider=self.name,
                    model=str(payload["model"]),
                    operation="image",
                    units=1,
                    unit_label="image",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ),
            )

        return await with_retries(call, attempts=2)

    async def list_models(self, *, refresh: bool = False) -> list[dict[str, object]]:
        """Models the endpoint advertises (``GET {base}/models``). Many image gateways omit images
        from this list, so an empty result is not an error."""
        try:
            async with default_client(20) as client:
                resp = await client.get(
                    f"{self._base}/models", headers={"Authorization": f"Bearer {self._key}"}
                )
            if resp.status_code != 200:
                return []
            body = resp.json()
            rows = body.get("data") if isinstance(body, dict) else body
            models = [
                {"id": str(r["id"]), "name": str(r.get("id"))}
                for r in rows or []
                if isinstance(r, dict) and r.get("id")
            ]
            return sorted(models, key=lambda m: str(m["id"]))
        except Exception:  # noqa: BLE001 - discovery is best effort
            return []

    async def health(self) -> tuple[bool, str]:
        try:
            async with default_client(15) as client:
                resp = await client.get(
                    f"{self._base}/models", headers={"Authorization": f"Bearer {self._key}"}
                )
            if resp.status_code == 200:
                count = len((resp.json() or {}).get("data") or [])
                return True, f"Connected · {count} models listed"
            if resp.status_code in (401, 403):
                return False, f"Authentication rejected (HTTP {resp.status_code})"
            # 404: generation may still work on endpoints without a model list.
            return True, f"Endpoint reachable (HTTP {resp.status_code}); model list unavailable"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"


class GeminiImage:
    name = "gemini"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._base = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        aspect_ratio: str = "16:9",
        model: str | None = None,
        reference_image: bytes | None = None,
        seed: int | None = None,
        timeout_s: float = 180.0,
    ) -> GeneratedImage:
        started = time.perf_counter()
        model_id = model or "gemini-2.5-flash-image"
        full_prompt = prompt if not negative_prompt else f"{prompt}. Do not depict: {negative_prompt}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        async def call() -> GeneratedImage:
            async with default_client(timeout_s) as client:
                resp = await client.post(
                    f"{self._base}/models/{model_id}:generateContent",
                    headers={"x-goog-api-key": self._key},
                    json=payload,
                )
            raise_for_status(resp, self.name)
            candidates = resp.json().get("candidates") or []
            for part in candidates[0].get("content", {}).get("parts", []) if candidates else []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline:
                    data = base64.b64decode(inline["data"])
                    w, h = ASPECT_TO_SIZE.get(aspect_ratio, ASPECT_TO_SIZE["16:9"])
                    return GeneratedImage(
                        data=data,
                        mime=inline.get("mimeType", "image/png"),
                        width=w,
                        height=h,
                        usage=Usage(
                            provider=self.name,
                            model=model_id,
                            operation="image",
                            units=1,
                            unit_label="image",
                            latency_ms=int((time.perf_counter() - started) * 1000),
                        ),
                    )
            raise ProviderError("Gemini image response contained no image data")

        return await with_retries(call, attempts=2)

    async def health(self) -> tuple[bool, str]:
        try:
            async with default_client(15) as client:
                resp = await client.get(f"{self._base}/models", headers={"x-goog-api-key": self._key})
            return (resp.status_code == 200, f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"


class MockImage:
    """Pillow-drawn storyboard cards.

    Deterministic per prompt so scene regeneration is stable. Clearly watermarked ``MOCK``.
    """

    name = "mock"
    _palette = [
        ("#D6FF45", "#111111"),
        ("#F5F5F2", "#111111"),
        ("#111111", "#D6FF45"),
        ("#E8B94B", "#111111"),
    ]

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        aspect_ratio: str = "16:9",
        model: str | None = None,
        reference_image: bytes | None = None,
        seed: int | None = None,
        timeout_s: float = 30.0,
    ) -> GeneratedImage:
        from PIL import Image, ImageDraw, ImageFont

        w, h = ASPECT_TO_SIZE.get(aspect_ratio, ASPECT_TO_SIZE["16:9"])
        digest = hashlib.sha256(f"{prompt}|{seed}".encode()).digest()
        bg, fg = self._palette[digest[0] % len(self._palette)]
        img = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("georgia.ttf", int(h * 0.075))
            mono_font = ImageFont.truetype("consola.ttf", int(h * 0.022))
        except OSError:
            title_font = ImageFont.load_default(size=int(h * 0.075))
            mono_font = ImageFont.load_default(size=int(h * 0.022))

        # editorial framing: rule grid + oversized scene number
        step = h // 9
        for x in range(0, w, step):
            draw.line([(x, 0), (x, h)], fill=fg, width=1)
        for y in range(0, h, step):
            draw.line([(0, y), (w, y)], fill=fg, width=1)
        margin = int(h * 0.08)
        draw.rectangle([margin, margin, w - margin, h - margin], outline=fg, width=max(2, h // 260))
        draw.text((margin * 2, margin * 1.4), "MOCK ASSET", font=mono_font, fill=fg)

        words = prompt.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=title_font) > w - margin * 4:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        y = int(h * 0.36)
        for line in lines[:4]:
            draw.text((margin * 2, y), line, font=title_font, fill=fg)
            y += int(h * 0.09)
        draw.text(
            (margin * 2, h - margin * 1.8),
            "placeholder · configure an image provider in Providers",
            font=mono_font,
            fill=fg,
        )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return GeneratedImage(
            data=buffer.getvalue(),
            mime="image/png",
            width=w,
            height=h,
            usage=Usage(provider=self.name, model="mock-image", operation="image", units=1,
                        unit_label="image", latency_ms=25),
        )

    async def health(self) -> tuple[bool, str]:
        return True, "Mock image provider · Pillow"


def build_image_provider(
    slug: str,
    api_key: str | None,
    base_url: str | None,
    *,
    options: dict[str, str] | None = None,
    label: str | None = None,
) -> ImageProvider:
    if slug == "mock":
        return MockImage()
    if not api_key:
        raise ProviderError(f"Image provider '{slug}' has no credential configured")
    if slug in ("openai", "openai-compatible"):
        return OpenAIImage(
            api_key,
            base_url or "https://api.openai.com/v1",
            options=options,
            label=label or ("OpenAI-compatible images" if slug == "openai-compatible" else "OpenAI Images"),
        )
    if slug == "gemini":
        return GeminiImage(api_key)
    raise ProviderError(f"Unsupported image provider '{slug}'")
