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
        "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'no_data'",
        """CREATE TABLE IF NOT EXISTS user_favorites (
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        hive_id INTEGER REFERENCES beehives(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, hive_id)
        )""",
        """CREATE TABLE IF NOT EXISTS alerts (
         id SERIAL PRIMARY KEY,
        hive_id INTEGER REFERENCES beehives(id) ON DELETE CASCADE,
        old_status VARCHAR(20) NOT NULL,
        new_status VARCHAR(20) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS source VARCHAR(50) NOT NULL DEFAULT 'manual'",
        """CREATE TABLE IF NOT EXISTS user_alert_reads (
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, alert_id)
        )""",
    ]
    for sql in migrations:
        conn.execute(text(sql))
    conn.commit()
print("Migration OK")