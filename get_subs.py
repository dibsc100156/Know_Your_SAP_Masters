import subprocess, sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
video_url = "https://www.youtube.com/watch?v=2Muxy3wE-E0"
out_dir = "C:/Users/vishnu/.openclaw/workspace/SAP_HANA_LLM_VendorChatbot"
r = subprocess.run(
    [sys.executable, "-m", "yt_dlp",
     "--write-auto-subs", "--sub-lang", "en",
     "--skip-download",
     "--output", f"{out_dir}/s3.%(ext)s",
     video_url],
    capture_output=True, timeout=120, encoding='utf-8', errors='replace'
)
print("RC:", r.returncode)
print("OUT:", r.stdout[:2000] if r.stdout else "None")
print("ERR:", r.stderr[:1000] if r.stderr else "None")
