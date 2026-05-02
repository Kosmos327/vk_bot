from typing import Optional


def extract_attachment_url(message: dict) -> Optional[str]:
    for attachment in message.get("attachments", []):
        if attachment.get("type") == "photo":
            sizes = attachment.get("photo", {}).get("sizes", [])
            if not sizes:
                continue
            best = max(sizes, key=lambda item: item.get("width", 0) * item.get("height", 0))
            url = best.get("url")
            if url:
                return url
        if attachment.get("type") == "doc":
            url = attachment.get("doc", {}).get("url")
            if url:
                return url
    return None
