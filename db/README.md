# Local database directory

`postgres-data/` is the bind mount for the local PostgreSQL container:

```
./db/postgres-data  ->  /var/lib/postgresql/data
```

Keeping it in the repository rather than in a named Docker volume means
`docker compose down` leaves your local data alone, and you can see where it
lives. The directory contents are git-ignored — PostgreSQL's data files must
never be committed.

To start completely fresh, stop the stack and delete the directory's contents:

```bash
docker compose down
rm -rf db/postgres-data/pgdata
docker compose up --build
```

Production data lives in the Railway PostgreSQL service and has nothing to do
with this directory.
