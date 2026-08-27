import sqlite3, time, os
from pathlib import Path
DB=Path(os.getenv('XFI_AI_DB','/var/lib/xfi-ai/keys.db'))
def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(DB) as c:
  c.execute('CREATE TABLE IF NOT EXISTS key_limits (key_hash TEXT PRIMARY KEY,name TEXT NOT NULL,rpm INTEGER DEFAULT 60,daily INTEGER DEFAULT 10000,enabled INTEGER DEFAULT 1,requests_today INTEGER DEFAULT 0,day INTEGER DEFAULT 0,last_request REAL DEFAULT 0)')
  c.commit()
def check(key_hash):
 init(); now=time.time(); day=int(now//86400)
 with sqlite3.connect(DB) as c:
  r=c.execute('SELECT rpm,daily,enabled,requests_today,day,last_request FROM key_limits WHERE key_hash=?',(key_hash,)).fetchone()
  if not r:return True
  rpm,daily,enabled,count,stored_day,last=r
  if not enabled:return False
  if stored_day!=day: count=0; c.execute('UPDATE key_limits SET requests_today=0,day=? WHERE key_hash=?',(day,key_hash))
  if count>=daily:return False
  if now-last < 60/max(rpm,1):return False
  c.execute('UPDATE key_limits SET requests_today=requests_today+1,last_request=? WHERE key_hash=?',(now,key_hash));c.commit();return True
