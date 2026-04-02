import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TokenResolution:
    token: str
    source: str


class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, token: str) -> None:
        self.path.write_text(json.dumps({"openai_api_key": token}), encoding="utf-8")

    def load(self) -> str | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload.get("openai_api_key")

    def resolve(self, client_token: str | None) -> TokenResolution:
        if client_token:
            return TokenResolution(token=client_token, source="client")
        saved_token = self.load()
        if saved_token:
            return TokenResolution(token=saved_token, source="server")
        raise ValueError("Nenhum token OpenAI foi informado ou salvo no servidor.")

