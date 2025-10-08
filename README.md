# ontonology-aware-llm
docker-compose up -d db

docker-compose up --build api

# Check logs
docker-compose logs -f db


# Cleanup
docker compose down -v
