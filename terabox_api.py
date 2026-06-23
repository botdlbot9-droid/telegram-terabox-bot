import requests
import json
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TeraBoxClient:
    def __init__(self):
        # अपना ndus cookie (जो तुमने पहले निकाला था)
        self.ndus = "YfX0nuMteHuiz2C6FldTYnK9ZHAl8TwK352_fecQ"
        self.base_url = "https://www.terabox.com"
        self.api_url = "https://www.terabox.com/api"
        self.app_id = "250528"
        self.js_token = None
        self.session = requests.Session()
        
        # Cookie set करो
        self.session.cookies.set("ndus", self.ndus, domain=".terabox.com")
        
        # Headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.terabox.com/",
            "Origin": "https://www.terabox.com"
        })
        
        # jsToken fetch करो
        self._refresh_js_token()
        logger.info("✅ TeraBox Client Ready")

    def _refresh_js_token(self):
        """ndus से jsToken निकालो"""
        try:
            url = f"{self.api_url}/list"
            params = {"app_id": self.app_id, "path": "/"}
            resp = self.session.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errno") == 0:
                    self.js_token = data.get("jsToken")
                    logger.info(f"✅ jsToken fetched: {self.js_token[:10]}...")
                else:
                    logger.error(f"❌ jsToken error: {data}")
            else:
                logger.error(f"❌ jsToken status: {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ jsToken fetch error: {e}")

    def _get_params(self, extra: dict = None) -> dict:
        params = {"app_id": self.app_id}
        if self.js_token:
            params["jsToken"] = self.js_token
        if extra:
            params.update(extra)
        return params

    def _request(self, method, endpoint, params=None, data=None, files=None):
        """सभी requests को send करने का common method"""
        url = f"{self.api_url}/{endpoint}"  # endpoint = "precreate", "upload", "create", etc.
        params = params or {}
        params.update(self._get_params())
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.terabox.com/",
            "Origin": "https://www.terabox.com"
        }
        if files:
            # for multipart upload
            resp = self.session.post(url, params=params, files=files, headers=headers)
        elif method.upper() == "POST":
            resp = self.session.post(url, params=params, data=data, headers=headers)
        else:
            resp = self.session.get(url, params=params, headers=headers)
        return resp

    def list_files(self, path="/", limit=100) -> List[Dict]:
        resp = self._request("GET", "list", params={"path": path, "limit": limit, "order": "time", "desc": 1})
        if resp.status_code != 200:
            raise Exception(f"List error: {resp.status_code} - {resp.text[:200]}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"List error: {data.get('msg')}")
        return data.get("data", {}).get("list", [])

    def upload_file(self, file_path, remote_path="/") -> Dict:
        if not os.path.exists(file_path):
            raise Exception("File not found")
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        logger.info(f"📤 Uploading {file_name} ({file_size} bytes)")

        # Step 1: Pre-create (endpoint: precreate)
        resp = self._request("POST", "precreate", data={
            "filename": file_name,
            "path": remote_path,
            "size": file_size,
            "uploadid": "",
            "target": "l1"
        })
        if resp.status_code != 200:
            raise Exception(f"Pre-create failed: {resp.status_code} - {resp.text}")
        result = resp.json()
        if result.get("errno") != 0:
            raise Exception(f"Pre-create error: {result.get('msg')}")

        pre_data = result.get("data", {})
        # Rapid upload if already exists
        if pre_data.get("return_type") == 2:
            logger.info("⚡ File already exists, rapid upload")
            return {"success": True, "message": "Rapid upload", "data": pre_data}

        upload_id = pre_data.get("uploadid")
        chunk_size = 4 * 1024 * 1024
        total_chunks = (file_size + chunk_size - 1) // chunk_size

        # Step 2: Upload chunks (endpoint: upload)
        with open(file_path, 'rb') as f:
            for i in range(total_chunks):
                chunk = f.read(chunk_size)
                files = {"file": (file_name, chunk, "application/octet-stream")}
                params = {"path": remote_path, "uploadid": upload_id, "partseq": i + 1}
                resp = self._request("POST", "upload", params=params, files=files)
                if resp.status_code != 200:
                    raise Exception(f"Chunk {i+1} failed: {resp.status_code} - {resp.text}")
                up_result = resp.json()
                if up_result.get("errno") != 0:
                    raise Exception(f"Chunk {i+1} error: {up_result.get('msg')}")
                logger.info(f"📦 Chunk {i+1}/{total_chunks} uploaded")

        # Step 3: Create file (endpoint: create)
        resp = self._request("POST", "create", data={
            "path": remote_path,
            "filename": file_name,
            "size": file_size,
            "uploadid": upload_id,
            "target": "l1"
        })
        if resp.status_code != 200:
            raise Exception(f"Create failed: {resp.status_code} - {resp.text}")
        create_result = resp.json()
        if create_result.get("errno") != 0:
            raise Exception(f"Create error: {create_result.get('msg')}")

        logger.info(f"✅ Upload complete: {file_name}")
        return {"success": True, "message": "Upload successful", "data": create_result.get("data", {})}

    def download_file(self, file_id) -> bytes:
        resp = self._request("GET", "locatedownload", params={"fs_id": file_id, "target": "l1"})
        if resp.status_code != 200:
            raise Exception(f"Get download link error: {resp.status_code} - {resp.text}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"Download link error: {data.get('msg')}")
        dlink = data.get("data", {}).get("dlink")
        if not dlink:
            raise Exception("No dlink")
        dl = self.session.get(dlink, headers={"User-Agent": "Mozilla/5.0"})
        if dl.status_code != 200:
            raise Exception(f"Download failed: {dl.status_code}")
        return dl.content

    def delete_file(self, file_id) -> bool:
        resp = self._request("POST", "filemanager", params={"action": "delete", "target": "l1"}, data={"filelist": json.dumps([file_id])})
        if resp.status_code != 200:
            raise Exception(f"Delete error: {resp.status_code}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"Delete error: {data.get('msg')}")
        return True

    def create_folder(self, folder_name, path="/") -> bool:
        resp = self._request("POST", "filemanager", params={"action": "mkdir", "target": "l1"}, data={"path": path, "name": folder_name})
        if resp.status_code != 200:
            raise Exception(f"Create folder error: {resp.status_code}")
        data = resp.json()
        if data.get("errno") != 0:
            raise Exception(f"Create folder error: {data.get('msg')}")
        return True
