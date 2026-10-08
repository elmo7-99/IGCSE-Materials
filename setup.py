"""Create local development credentials; never overwrite an existing .env."""
import secrets
from pathlib import Path
root=Path(__file__).resolve().parent
path=root/'.env'
if path.exists():raise SystemExit('.env already exists; review it instead of overwriting it')
s=(root/'.env.example').read_text(encoding='utf-8-sig').replace('ADMIN_API_KEY=\n','ADMIN_API_KEY='+secrets.token_urlsafe(32)+'\n').replace('INTAKE_API_KEY=\n','INTAKE_API_KEY='+secrets.token_urlsafe(32)+'\n')
path.write_text(s,encoding='utf-8');path.chmod(0o600)
print('Local dry-run configuration created. Read ADMIN_API_KEY from .env locally, then run python3 server.py.')
