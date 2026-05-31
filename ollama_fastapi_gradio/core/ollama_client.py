import httpx

class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def generate(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        temperature: float,
        top_p: float,
        num_predict: int,
    ) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": num_predict,
            },
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json().get("response", "")
