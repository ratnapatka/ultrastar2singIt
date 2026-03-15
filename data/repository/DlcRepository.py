import sqlite3
import os
from typing import Optional, List

from data.entity.DlcEntity import DlcEntity

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

def _get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)

def init():
    with _get_connection() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS dlc (
                dlc_id TEXT PRIMARY KEY,
                dlc_name TEXT,
                dlc_json_name TEXT,
                core_id TEXT,
                core_edition TEXT
            )""")

        c.execute("SELECT COUNT(1) FROM dlc")
        if c.fetchone()[0] == 0:
            data = (('0100CC30149B9002','Best of 80s Vol 1 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9007','Best of 80s Vol 2 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B900A','Best of 80s Vol 3 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9006','Best of 90s Vol 1 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9008','Best of 90s Vol 2 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9011','Best of 90s Vol 3 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9003','Chart Hits Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B900B','Classic Rock Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9009','Country Hits Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B900D','French Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B900E','German Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B900C','International Songs',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9005','Legendary Hits Vol 1 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9010','Legendary Hits Vol 2 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9001','Party Classics Vol 1 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B9004','Party Classics Vol 2 Song Pack',None,'0100CC30149B8000','2022'),
            ('0100CC30149B900F','Spanish Song Pack',None,'0100CC30149B8000','2022'),
            ('0100D7701692F002','Best of 80s Vol. 1 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F007','Best of 80s Vol. 2 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F00A','Best of 80s Vol. 3 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F006','Best of 90s Vol. 1 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F008','Best of 90s Vol. 2 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F011','Best Of 90s Vol. 3 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F003','Chart Hits Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F013','Christmas Hits Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F00B','Classic Rock Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F009','Country Hits Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F014','Eurovision Hits Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F00C','International Song Pack ',None,'0100D7701692E000','2023'),
            ('0100D7701692F005','Legendary Hits Vol. 1 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F010','Legendary Hits Vol. 2 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F001','Party Classics Vol. 1 Song Pack',None,'0100D7701692E000','2023'),
            ('0100D7701692F004','Party Classics Vol. 2 Song Pack',None,'0100D7701692E000','2023'),
            ('0100AAF018059005','Canciones Espanolas','songs_spa','0100AAF018058000','2024'),
            ('0100AAF018059003','Deutschen Hits','songs_ger','0100AAF018058000','2024'),
            ('0100AAF018059002','Hits Francais et Internationaux','songs_fr','0100AAF018058000','2024'),
            ('0100AAF018059001','Hits from Australia and NZ','songs_aus','0100AAF018058000','2024'),
            ('0100AAF018059004','International Hits','songs_int','0100AAF018058000','2024'),
            ('01001C101ED11002','French Hits','songs_fr','01001C101ED10000','2025'))
            c.executemany("insert into dlc values (?,?,?,?,?)", data)

def get_by_dlc_id(dlc_id: str) -> Optional[DlcEntity]:
    with _get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM dlc WHERE dlc_id = ?", (dlc_id,))
        row = c.fetchone()
        return DlcEntity(*row) if row else None

def get_edition_by_core_id(core_id: str) -> Optional[str]:
    with _get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT distinct core_edition FROM dlc WHERE core_id = ?", (core_id,))
        edition = c.fetchone()
        return edition[0] if edition else 'other'

def get_all() -> List[DlcEntity]:
    with _get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM dlc")
        rows = c.fetchall()
        return [DlcEntity(*row) for row in rows]

def get_by_core_edition(core_edition: str) -> List[DlcEntity]:
    with _get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM dlc WHERE core_edition = ?", (core_edition,))
        rows = c.fetchall()
        return [DlcEntity(*row) for row in rows]

def get_core_editions() -> List[DlcEntity]:
    with _get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT core_edition, core_id FROM dlc ORDER BY core_edition DESC")
        rows = c.fetchall()
        return [DlcEntity(core_id=row[1], core_edition=row[0]) for row in rows]

# print(get_by_dlc_id('0100CC30149B9009'))
# list = get_by_core_edition('2024')
# filtered = [e for e in list if e.dlc_json_name == 'songs_spa']
# print(filtered)
# list = get_all()
# print(sorted({e.core_edition for e in list}))
