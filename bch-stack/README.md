# BCH Local Stack (Scaffold)

Single container scaffold for:
- Bitcoin Cash Node (BCHN) `bitcoind` (pruned node)
- `ckpool` (BCH `sha256d`)
- Manager UI/API (FastAPI)

This is an initial foundation to iterate from. It bootstraps config layout and gives a simple control UI.

## Persistent storage layout

All data is under `/config`:

- `/config/node`
- `/config/ckpool`
- `/config/ui`
- `/config/logs/node`
- `/config/logs/ckpool`
- `/config/logs/ui`
- `/config/backups`

## Run

```bash
docker compose -f bch-stack/docker-compose.yml up -d --build
```

Open manager UI:

- `http://localhost:8084`

## Notes

- Coin is fixed to `BCH`.
- Algorithm is fixed to `sha256d`.
- Default stratum port is `3334`.
- Node defaults to pruned mode (`prune=550`).
- Default `ckpool.conf` is seeded with placeholder upstream/address values and must be edited.
- `ckpool` stays running in a wait state until placeholders are replaced, then can be restarted from the manager API.
- `bitcoind` and `bitcoin-cli` are downloaded from BCHN v29.0.0 Linux release tarball during image build.
- `ckpool` binaries are built from `https://github.com/skaisser/ckpool` during image build.

## API

- `GET /health`
- `GET /api/status`
- `GET /api/config`
- `POST /api/config`
- `POST /api/restart/{service_name}`

## Integration API (`v1`)

- `GET /api/v1/capabilities`
- `GET /api/v1/services`
- `GET /api/v1/node/blockchain`
- `GET /api/v1/node/network`
- `GET /api/v1/node/mining`
- `GET /api/v1/ready`
- `GET /api/v1/ckpool/config`
- `GET /api/v1/ckpool/logs?lines=120`
- `GET /api/v1/ckpool/metrics`
- `GET /api/v1/events?since=2026-02-20T23:00:00&limit=200&order=asc&severity=error&event_type=system&source_contains=stderr`
- `GET /api/v1/events/cursor?since=2026-02-20T23:00:00&limit=200&order=asc&severity=error&event_type=system&source_contains=stderr`
- `GET /api/v1/snapshot?since=2026-02-20T23:00:00&limit=100`
- `GET /api/v1/snapshot/compact?since=2026-02-20T23:00:00&limit=200`