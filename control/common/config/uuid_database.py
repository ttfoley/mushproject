import json
import os
from pathlib import Path
from typing import Optional

class UUIDDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to project root/uuid_db.json
            db_path = str(Path(__file__).parent / "uuid_db.json")
        self.db_path = db_path
        self._load_or_create_db()

    def _load_or_create_db(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r') as f:
                self.addr_to_uuid = json.load(f)
            self._next_uuid = max(self.addr_to_uuid.values()) + 1
        else:
            self.addr_to_uuid = {}
            self._next_uuid = 0
            self._save_db()

    def get_uuid(self, addr: str) -> int:
        """Get or create UUID for address"""
        if addr not in self.addr_to_uuid:
            self.addr_to_uuid[addr] = self._next_uuid
            self._next_uuid += 1
            self._save_db()
        return self.addr_to_uuid[addr]

    def _save_db(self):
        with open(self.db_path, 'w') as f:
            json.dump(self.addr_to_uuid, f, indent=2, sort_keys=True) 