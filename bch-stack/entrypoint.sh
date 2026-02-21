#!/usr/bin/env sh
set -eu

mkdir -p /config/node /config/ckpool /config/ui
mkdir -p /config/logs/node /config/logs/ckpool /config/logs/ui
mkdir -p /config/backups

if [ ! -f /config/node/bitcoin.conf ]; then
  cat > /config/node/bitcoin.conf << 'EOF'
server=1
daemon=0
txindex=0
prune=550
rpcuser=bch
rpcpassword=change_me
rpcallowip=127.0.0.1
rpcbind=127.0.0.1
printtoconsole=1
EOF
fi

if ! grep -q '^prune=' /config/node/bitcoin.conf; then
  echo 'prune=550' >> /config/node/bitcoin.conf
fi

if [ ! -f /config/ckpool/ckpool.conf ]; then
  cat > /config/ckpool/ckpool.conf << 'EOF'
{
  "name": "bch-local",
  "coin": "bch",
  "algo": "sha256d",
  "btcd": [
    {
      "url": "127.0.0.1:8332",
      "auth": "bch",
      "pass": "change_me",
      "notify": true
    }
  ],
  "serverurl": [
    "0.0.0.0:3334"
  ],
  "startdiff": 42
}
EOF
fi

if [ ! -f /config/ui/settings.json ]; then
  cat > /config/ui/settings.json << 'EOF'
{
  "coin": "BCH",
  "algo": "sha256d",
  "label": "BCH Local Stack"
}
EOF
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf