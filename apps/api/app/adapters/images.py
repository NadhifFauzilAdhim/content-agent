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
}


class OpenAIImage:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")

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
        size = ASPECT_TO_SIZE.get(aspect_ratio, ASPECT_TO_SIZE["16:9"])
        payload = {
            "model": model or "gpt-image-1",
            "prompt": prompt if not negative_prompt else f"{prompt}\n\nAvoid: {negative_prompt}",
            "size": f"{size[0]}x{size[1]}",
            "n": 1,
        }
        if reference_image:
            payload["image"] = "data:image/png;base64," + base64.b64encode(reference_image).decode()

        async def call() -> GeneratedImage:
            async with default_client(timeout_s) as client:
                resp = await client.post(
                    f"{self._base}/images/generations",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=payload,
                )
            raise_for_status(resp, self.name)
            body = resp.json()
            b64 = body["data"][0].get("b64_json")
            if b64:
                data = base64.b64decode(b64)
            else:  # some models return a temporary URL
                async with default_client(timeout_s) as client:
                    img = await client.get(body["data"][0]["url"])
                data = img.content
            return GeneratedImage(
                data=data,
                mime="image/png",
                width=size[0],
                height=size[1],
                usage=Usage(
                    provider=self.name,
                    model=payload["model"],
                    operation="image",
                    units=1,
                    unit_label="image",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ),
            )

        return await with_retries(call, attempts=2)

    async def health(self) -> tuple[bool, str]:
        try:
            async with default_client(15) as client:
                resp = await client.get(
                    f"{self._base}/models", headers={"Authorization": f"Bearer {self._key}"}
                )
            return (resp.status_code == 200, f"HTTP {resp.status_code}")
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


def build_image_provider(slug: str, api_key: str | None, base_url: str | None) -> ImageProvider:
    if slug == "mock":
        return MockImage()
    if not api_key:
        raise ProviderError(f"Image provider '{slug}' has no credential configured")
    if slug == "openai":
        return OpenAIImage(api_key, base_url or "https://api.openai.com/v1")
    if slug == "gemini":
        return GeminiImage(api_key)
    raise ProviderError(f"Unsupported image provider '{slug}'")
