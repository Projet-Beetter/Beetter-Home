import os
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
engine = create_engine(url)

with engine.connect() as conn:
    migrations = [
        "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS street VARCHAR(200)",
        "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS city VARCHAR(100)",
        "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)",
        "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS latitude FLOAT",
        "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS longitude FLOAT",
        """CREATE TABLE IF NOT EXISTS user_favorites (
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        hive_id INTEGER REFERENCES beehives(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, hive_id)
        )""",
    ]
    for sql in migrations:
        conn.execute(text(sql))
    conn.commit()
print("Migration OK")