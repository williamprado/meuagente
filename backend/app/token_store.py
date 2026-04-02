import json
from dataclasses import dataclass
from pathlib import Path

GEMINI_MODEL_MIGRATIONS = {
    "gemini-1.5-pro": "gemini-2.5-flash",
    "gemini-2.0-flash": "gemini-2.5-flash",
    "gemini-2.0-flash-001": "gemini-2.5-flash",
    "gemini-2.0-flash-lite": "gemini-2.5-flash",
    "gemini-2.0-flash-lite-preview": "gemini-2.5-flash",
    "gemini-2.0-flash-lite-preview-02-05": "gemini-2.5-flash",
}


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

    def _normalize_model(self, provider: str, model: str | None) -> str:
        fallback = self.default_models[provider]
        if not model:
            return fallback
        if provider == "gemini":
            return GEMINI_MODEL_MIGRATIONS.get(model, model)
        return model

    def _normalize(self, payload: dict | None) -> dict:
        normalized = self._default_payload()
        if not isinstance(payload, dict):
            return normalized

        if "openai_api_key" in payload and "openai" not in payload and "gemini" not in payload:
            normalized["openai"]["api_key"] = payload.get("openai_api_key")
            normalized["openai"]["model"] = self._normalize_model("openai", payload.get("openai_model"))
            normalized["active_provider"] = payload.get("active_provider") or "openai"
            return normalized

        active_provider = payload.get("active_provider")
        if active_provider in {"openai", "gemini"}:
            normalized["active_provider"] = active_provider

        for provider in ("openai", "gemini"):
            provider_payload = payload.get(provider) or {}
            if isinstance(provider_payload, dict):
                normalized[provider]["api_key"] = provider_payload.get("api_key") or None
                normalized[provider]["model"] = self._normalize_model(
                    provider,
                    provider_payload.get("model"),
                )

            legacy_key = payload.get(f"{provider}_api_key")
            if legacy_key:
                normalized[provider]["api_key"] = legacy_key

            legacy_model = payload.get(f"{provider}_model")
            if legacy_model:
                normalized[provider]["model"] = self._normalize_model(provider, legacy_model)

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
            payload["openai"]["model"] = self._normalize_model("openai", openai_model)

        if gemini_api_key is not None:
            payload["gemini"]["api_key"] = gemini_api_key or None
        if gemini_model:
            payload["gemini"]["model"] = self._normalize_model("gemini", gemini_model)

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
        normalized = self._normalize(payload)
        if normalized != payload:
            self.path.write_text(json.dumps(normalized), encoding="utf-8")
        return normalized

    def _single_saved_provider(self, payload: dict) -> str | None:
        configured = [provider for provider in ("openai", "gemini") if payload[provider]["api_key"]]
        if len(configured) == 1:
            return configured[0]
        return None

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

        if not token:
            fallback_provider = self._single_saved_provider(payload)
            if fallback_provider and fallback_provider != active_provider:
                token = payload[fallback_provider]["api_key"]
                model = client_models[fallback_provider] or payload[fallback_provider]["model"]
                active_provider = fallback_provider
                source = "server"

        if token:
            return TokenResolution(
                provider=active_provider,
                token=token,
                model=model,
                source=source,
            )

        provider_label = "OpenAI" if active_provider == "openai" else "Gemini"
        raise ValueError(f"Nenhuma chave de API {provider_label} foi informada ou salva no servidor.")
