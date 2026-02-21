# BTC Local Stack (Scaffold)

Single container scaffold for:
- Bitcoin Core `bitcoind` (pruned node)
- `ckpool` (BTC `sha256d`)
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
docker compose -f btc-stack/docker-compose.yml up -d --build
```

### Host network (Linux)

If you want to avoid Docker bridge networking entirely (and you are running on Linux), you can run with host networking:

```bash
docker run -d \
	--name btc-local-stack \
	--network host \
	-v /data/btc-local-stack:/config \
	--restart unless-stopped \
	ghcr.io/renegadeuk/hmm-local-btc-stack:main
```

With `--network host`, the manager is on `http://<host>:8083` and stratum is on `<host>:3333`.

Open manager UI:

- `http://localhost:8083`

## Notes

- Coin is fixed to `BTC`.
- Algorithm is fixed to `sha256d`.
- Default stratum port is `3333`.
- Node defaults to pruned mode (`prune=550`).
- `bitcoind` RPC is bound to `127.0.0.1` and defaults to `rpcport=18332` to reduce host-network port collisions.
- P2P listening defaults to disabled (`listen=0`) so the stack can coexist with an existing host `bitcoind`.
- `ckpool` is configured to use `127.0.0.1:18332` for RPC inside the container.
- `bitcoind` and `bitcoin-cli` are downloaded from Bitcoin Core v28.0 Linux release tarball during image build.
- `ckpool` binaries are built from the bundled `_ref_ckpool` source during image build.

Last updated: 2026-02-21

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