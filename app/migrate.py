from app import create_app
from app.models import db

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        migrations = [
            "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS street VARCHAR(200)",
            "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS city VARCHAR(100)",
            "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)",
            "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS latitude FLOAT",
            "ALTER TABLE beehives ADD COLUMN IF NOT EXISTS longitude FLOAT",
        ]
        for sql in migrations:
            conn.execute(db.text(sql))
        conn.commit()
    print("Migration OK")
    