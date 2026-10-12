import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
export default function setup() {
  if (!process.env.E2E_DATABASE_URL)
    throw new Error(
      "Set E2E_DATABASE_URL to a migrated disposable PostgreSQL database ending in _test.",
    );
  process.env.E2E_ADMIN_EMAIL = `synthetic.browser.admin.${randomUUID().slice(0, 8)}@example.com`;
  process.env.E2E_ADMIN_PASSWORD = randomUUID() + randomUUID();
  const result = spawnSync(
    resolve("../backend/.venv/bin/python"),
    [
      "-c",
      `
import json, os, sys, base64
from io import BytesIO
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import User
from app.security import hash_password
from app.seed import seed_demo
from app.demo_images import seed_demo_images
data=json.load(sys.stdin)
engine=create_engine(os.environ['E2E_DATABASE_URL'])
if not engine.url.database.endswith('_test'): sys.exit('A disposable _test database is required')
with Session(engine) as s,s.begin():
    if os.environ.get('E2E_SEED_DEMO') == '1':
        password=os.environ.get('E2E_DEMO_PASSWORD', '')
        if not password: sys.exit('Set E2E_DEMO_PASSWORD when E2E_SEED_DEMO=1')
        seed_demo(s, password)
        seed_demo_images(s)
    s.add(User(email=data['email'],password_hash=hash_password(data['password']),full_name='Synthetic Browser Agent',role='admin'))
engine.dispose()
buffer=BytesIO(); Image.new('RGB',(16,16),'#dbe3b5').save(buffer,format='PNG')
print(base64.b64encode(buffer.getvalue()).decode())
`,
    ],
    {
      input: JSON.stringify({
        email: process.env.E2E_ADMIN_EMAIL,
        password: process.env.E2E_ADMIN_PASSWORD,
      }),
      encoding: "utf8",
      env: process.env,
    },
  );
  if (result.status !== 0)
    throw new Error(
      "Could not provision the synthetic browser test administrator. Check the migrated _test database and backend environment.",
    );
  process.env.E2E_IMAGE_PNG = result.stdout.trim();
}
