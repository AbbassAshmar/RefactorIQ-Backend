from app.models import *
from app.core.database import engine

def reset_db():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)

    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)

    print("Done.")

if __name__ == "__main__":
    reset_db()