import urllib.request
import os

url = "https://github.com/vercel/vercel/releases/latest/download/vercel-windows.exe"
print(f"Downloading Vercel CLI from {url}...")
urllib.request.urlretrieve(url, "vercel.exe")
print("Downloaded vercel.exe successfully.")
