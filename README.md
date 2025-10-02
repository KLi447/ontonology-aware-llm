# ontonology-aware-llm
# Start Postgres in background
docker-compose up -d

# Check logs
docker-compose logs -f db

python init_db.py
python init_memory_db.py