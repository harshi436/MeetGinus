# services/downloader.py
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

def download_mp3(url: str, bot_id: str, recordings_dir: str) -> str:
    """
    Stream-download the MP3 from Recall CDN and save it to recordings/{bot_id}.mp3

    Args:
        url            : Recall CDN download URL
        bot_id         : used as the filename ({bot_id}.mp3)
        recordings_dir : folder path where the file will be saved

    Returns:
        Absolute local file path of the saved MP3
    """
    # ── Ensure recordings/ folder exists ─────────────────────────────────────
    os.makedirs(recordings_dir, exist_ok=True)

    filename    = f"{bot_id}.mp3"
    output_path = os.path.join(recordings_dir, filename)

    print(f"⬇️  Downloading MP3 for bot {bot_id} ...")
    print(f"   URL             : {url}")
    print(f"   Save path       : {output_path}")

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    # ── Validate saved file ───────────────────────────────────────────────────
    if not os.path.exists(output_path):
        raise Exception(f"❌ File was not saved: {output_path}")

    if os.path.getsize(output_path) == 0:
        raise Exception(f"❌ File downloaded but is empty: {output_path}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ MP3 saved: {output_path}  ({size_mb:.2f} MB)")

    return output_path