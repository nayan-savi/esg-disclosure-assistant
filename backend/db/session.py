from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create database engine using the configured PostgreSQL URL
# pool_pre_ping checks connection health before issuing queries
engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    FastAPI dependency to yield a database session and close it afterwards.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_connection() -> bool:
    """
    Executes a simple 'SELECT 1' query to verify the database is online and reachable.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection check failed: {e}")
        return False

def init_db():
    """
    Initializes required database tables (e.g. upload_request) if they do not exist.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS upload_request (
                    id BIGSERIAL PRIMARY KEY,
                    request_id BIGINT UNIQUE NOT NULL,
                    folder_path VARCHAR(255),
                    total_files INT DEFAULT 0,
                    status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("""
                ALTER TABLE upload_request ADD COLUMN IF NOT EXISTS report_data TEXT;
            """))
            conn.execute(text("""
                ALTER TABLE upload_request ADD COLUMN IF NOT EXISTS model VARCHAR(50) DEFAULT 'gemini-3.5';
            """))
            conn.execute(text("""
                ALTER TABLE upload_request ADD COLUMN IF NOT EXISTS name VARCHAR(255);
            """))
            conn.execute(text("""
                ALTER TABLE upload_request ADD COLUMN IF NOT EXISTS framework_name VARCHAR(255) DEFAULT 'VSME (Voluntary Sustainability Reporting Standard for SMEs)';
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS framework_document (
                    id BIGSERIAL PRIMARY KEY,
                    doc_id VARCHAR(100) UNIQUE NOT NULL,
                    framework_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    file_name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_size VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
        print("Database tables checked/created successfully.")
    except Exception as e:
        print(f"Failed to initialize database tables: {e}")

