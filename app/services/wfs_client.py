from __future__ import annotations


class WFSClient:
    """Placeholder for future VWorld WFS integration."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def download_layer(self, layer_name: str, filters: dict | None = None) -> None:
        raise NotImplementedError("WFS integration is planned for the next phase.")
