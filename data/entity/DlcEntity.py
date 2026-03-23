from dataclasses import dataclass
from typing import Optional

@dataclass
class DlcEntity:
    dlc_id: str = None
    dlc_name: str = None
    dlc_json_name: Optional[str] = None
    core_id: str = None
    core_edition: str = None