import requests
import json
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TeraBoxClient:
    def __init__(self):
        # आपका ndus cookie (हमेशा वैलिड रहेगा)
        self.ndus = "YfX0nuMteHuiz2C6FldTYnK9ZHAl8TwK352_fecQ"
        self.base_url = "https://www.terabox.com"
        self.api_url = "https://www.terabox.com/api"
        self.app_id = "250528"
        self.js_token = None
        self.session = requests.Session()
        
        # 1. ndus cookie सेट करो
        self.session.cookies.set("ndus", self.ndus, domain=".terabox.com")
        
        # 2. Browser Headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.terabox.com/",
            "Origin": "https://www.terabox.com"
        })
        
        # 3. सबसे जरूरी: API call से jsToken निकालो (बिना login के)
        self._refresh_js_token()
        logger.info("✅ TeraBox Client Ready with ndus & jsToken")

    def _refresh_js_token(self):
        """ndus cookie की मदद से jsToken निकालो"""
        try:
            url = f"{self.api_url}/list"
            params = {"app_id": self.app_id, "path": "/"}
            resp = self.session.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errno") == 0:
                    self.js_token = data.get("jsToken")
                    logger.info(f"✅ jsToken fetched successfully: {self.js_token[:10]}...")
                else:
                    logger.error(f"❌ Failed to fetch jsToken: {data.get('msg')}")
            else:
                logger.error(f"❌ Failed to fetch jsToken: Status {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ jsToken fetch error: {e}")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.terabox.com/",
            "Origin": "https://www.terabox.com"
        }

    def _get_params(self, extra: dict = None) -> dict:
        # हर request में jsToken जरूर भेजो
        params = {"app_id": self.app_id}
        if self.js_token:
            params["jsToken"] = self.js_token
        if extra:
            params.update(extra)
        return params

    def list_files(self, path: str = "/", limit: int = 100) -> List[Dict[str, Any]]:
        url = f"{self.api_url}/list"
        params = self._get_params({
            "path": path,
            "limit": limit,
            "order": "time",
            "desc": 1
        })
        resp = self.session.get(url, params=params, headers=self._get_headers())
        
        # अगर jsToken expire हो गया तो रिफ्रेश करो
        if resp.status_code == 401 or "jsToken" in resp.text:
            self._refresh_js_token()
            params = self._get_params({"path": path, "limit": limit, "order": "time", "desc": 1})
            resp = self.session.get(url, params=params, headers=self._get_headers())
        
        if resp.status_code != 200:
            raise Exception(f"List failed: {resp.status_code} - {resp.text[:200]}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"List failed: {data.get('msg')}")
        return data.get("data", {}).get("list", [])

    def upload_file(self, file_path: str, remote_path: str = "/") -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        logger.info(f"📤 Uploading {file_name} ({file_size} bytes)")

        # ----- Step 1: Pre-create -----
        precreate_url = f"{self.api_url}/precreateFile"
        params = self._get_params()
        data = {
            "filename": file_name,
            "path": remote_path,
            "size": file_size,
            "uploadid": "",
            "target": "l1"
        }
        resp = self.session.post(precreate_url, params=params, data=data, headers=self._get_headers())
        if resp.status_code != 200:
            raise Exception(f"Pre-create failed: {resp.status_code}")
        result = resp.json()
        if result.get("errno") != 0:
            raise Exception(f"Pre-create error: {result.get('msg')}")
        
        precreate_data = result.get("data", {})
        # Rapid Upload (duplicate file)
        if precreate_data.get("return_type") == 2:
            logger.info("⚡ File already exists, using rapid upload")
            return {"success": True, "message": "File already exists (rapid upload)", "data": precreate_data}
        
        upload_id = precreate_data.get("uploadid")
        chunk_size = 4 * 1024 * 1024  # 4MB chunks
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        # ----- Step 2: Upload Chunks -----
        with open(file_path, 'rb') as f:
            for i in range(total_chunks):
                chunk = f.read(chunk_size)
                upload_url = f"{self.api_url}/upload"
                files = {"file": (file_name, chunk, "application/octet-stream")}
                params_upload = self._get_params({
                    "path": remote_path,
                    "uploadid": upload_id,
                    "partseq": i + 1
                })
                resp = self.session.post(upload_url, params=params_upload, files=files, headers=self._get_headers())
                if resp.status_code != 200:
                    raise Exception(f"Chunk {i+1} upload failed: {resp.status_code}")
                upload_result = resp.json()
                if upload_result.get("errno") != 0:
                    raise Exception(f"Chunk {i+1} upload error: {upload_result.get('msg')}")
                logger.info(f"📦 Uploaded chunk {i+1}/{total_chunks}")

        # ----- Step 3: Create File -----
        create_url = f"{self.api_url}/createFile"
        params_create = self._get_params()
        create_data = {
            "path": remote_path,
            "filename": file_name,
            "size": file_size,
            "uploadid": upload_id,
            "target": "l1"
        }
        resp = self.session.post(create_url, params=params_create, data=create_data, headers=self._get_headers())
        if resp.status_code != 200:
            raise Exception(f"Create file failed: {resp.status_code}")
        create_result = resp.json()
        if create_result.get("errno") != 0:
            raise Exception(f"Create file error: {create_result.get('msg')}")
        
        logger.info(f"✅ Upload complete: {file_name}")
        return {"success": True, "message": "Upload successful", "data": create_result.get("data", {})}

    def download_file(self, file_id: str) -> bytes:
        url = f"{self.api_url}/locatedownload"
        params = self._get_params({"fs_id": file_id, "target": "l1"})
        resp = self.session.get(url, params=params, headers=self._get_headers())
        if resp.status_code != 200:
            raise Exception(f"Get download link failed: {resp.status_code}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"Download link error: {data.get('msg')}")
        dlink = data.get("data", {}).get("dlink")
        if not dlink:
            raise Exception("No download link found")
        dl_resp = self.session.get(dlink, headers={"User-Agent": "Mozilla/5.0"})
        if dl_resp.status_code != 200:
            raise Exception(f"Download failed: {dl_resp.status_code}")
        return dl_resp.content

    def delete_file(self, file_id: str) -> bool:
        url = f"{self.api_url}/filemanager"
        params = self._get_params({"action": "delete", "target": "l1"})
        payload = {"filelist": json.dumps([file_id])}
        resp = self.session.post(url, params=params, data=payload, headers=self._get_headers())
        if resp.status_code != 200:
            raise Exception(f"Delete failed: {resp.status_code}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"Delete error: {data.get('msg')}")
        return True

    def create_folder(self, folder_name: str, path: str = "/") -> bool:
        url = f"{self.api_url}/filemanager"
        params = self._get_params({"action": "mkdir", "target": "l1"})
        payload = {"path": path, "name": folder_name}
        resp = self.session.post(url, params=params, data=payload, headers=self._get_headers())
        if resp.status_code != 200:
            raise Exception(f"Create folder failed: {resp.status_code}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"Create folder error: {data.get('msg')}")
        return True
