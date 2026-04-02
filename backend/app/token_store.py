import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TokenResolution:
    provider: str
    token: str
    model: str
    source: str


class TokenStore:
    def __init__(
        self,
        path: Path,
        *,
        default_provider: str,
        openai_model: str,
        gemini_model: str,
    ) -> None:
        self.path = path
        self.default_provider = default_provider if default_provider in {"openai", "gemini"} else "openai"
        self.default_models = {
            "openai": openai_model,
            "gemini": gemini_model,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _default_payload(self) -> dict:
        return {
            "active_provider": self.default_provider,
            "openai": {
                "api_key": None,
                "model": self.default_models["openai"],
            },
            "gemini": {
                "api_key": None,
                "model": self.default_models["gemini"],
            },
        }

    def _normalize(self, payload: dict | None) -> dict:
        normalized = self._default_payload()
        if not isinstance(payload, dict):
            return normalized

        if "openai_api_key" in payload and "openai" not in payload and "gemini" not in payload:
            normalized["openai"]["api_key"] = payload.get("openai_api_key")
            normalized["openai"]["model"] = payload.get("openai_model") or self.default_models["openai"]
            normalized["active_provider"] = payload.get("active_provider") or "openai"
            return normalized

        active_provider = payload.get("active_provider")
        if active_provider in {"openai", "gemini"}:
            normalized["active_provider"] = active_provider

        for provider in ("openai", "gemini"):
            provider_payload = payload.get(provider) or {}
            if isinstance(provider_payload, dict):
                normalized[provider]["api_key"] = provider_payload.get("api_key") or None
                normalized[provider]["model"] = (
                    provider_payload.get("model") or self.default_models[provider]
                )

            legacy_key = payload.get(f"{provider}_api_key")
            if legacy_key:
                normalized[provider]["api_key"] = legacy_key

            legacy_model = payload.get(f"{provider}_model")
            if legacy_model:
                normalized[provider]["model"] = legacy_model

        return normalized

    def save(
        self,
        *,
        active_provider: str,
        openai_api_key: str | None = None,
        openai_model: str | None = None,
        gemini_api_key: str | None = None,
        gemini_model: str | None = None,
    ) -> dict:
        payload = self.load_config()
        if active_provider in {"openai", "gemini"}:
            payload["active_provider"] = active_provider

        if openai_api_key is not None:
            payload["openai"]["api_key"] = openai_api_key or None
        if openai_model:
            payload["openai"]["model"] = openai_model

        if gemini_api_key is not None:
            payload["gemini"]["api_key"] = gemini_api_key or None
        if gemini_model:
            payload["gemini"]["model"] = gemini_model

        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def load(self) -> str | None:
        payload = self.load_config()
        active_provider = payload["active_provider"]
        return payload[active_provider]["api_key"]

    def load_config(self) -> dict:
        if not self.path.exists():
            return self._default_payload()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return self._normalize(payload)

    def resolve(
        self,
        *,
        provider: str | None,
        openai_api_key: str | None,
        openai_model: str | None,
        gemini_api_key: str | None,
        gemini_model: str | None,
    ) -> TokenResolution:
        payload = self.load_config()
        active_provider = provider if provider in {"openai", "gemini"} else payload["active_provider"]

        client_tokens = {
            "openai": openai_api_key,
            "gemini": gemini_api_key,
        }
        client_models = {
            "openai": openai_model,
            "gemini": gemini_model,
        }

        token = client_tokens[active_provider] or payload[active_provider]["api_key"]
        model = client_models[active_provider] or payload[active_provider]["model"]
        source = "client" if client_tokens[active_provider] else "server"

        if token:
            return TokenResolution(
                provider=active_provider,
                token=token,
                model=model,
                source=source,
            )

        provider_label = "OpenAI" if active_provider == "openai" else "Gemini"
        raise ValueError(f"Nenhuma chave de API {provider_label} foi informada ou salva no servidor.")
