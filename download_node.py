import urllib.request
import zipfile
import os

url = "https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip"
print(f"Downloading Node.js from {url}...")
urllib.request.urlretrieve(url, "node.zip")
print("Downloaded node.zip successfully.")

print("Extracting...")
with zipfile.ZipFile("node.zip", 'r') as zip_ref:
    zip_ref.extractall(".")
print("Extracted successfully.")
