from sqlalchemy_schemadisplay import create_schema_graph
from sqlalchemy import create_engine
from app.models.base import Base

# Replace with your actual connection string
engine = create_engine("postgresql://postgres:admin@localhost:5433/refactorIQ-Dev")

graph = create_schema_graph(
    metadata=Base.metadata,
    engine=engine,             # pass the engine object, not a string
    show_datatypes=True,       # show column types
    show_indexes=False,        # skip indexes
    rankdir='LR',              # left-to-right layout
    concentrate=False          # avoid merging arrows
)

graph.write_png("erd.png")
