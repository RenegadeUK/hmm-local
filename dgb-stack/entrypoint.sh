#!/usr/bin/env sh
set -eu

mkdir -p /config/node /config/ckpool /config/ui
mkdir -p /config/logs/node /config/logs/ckpool /config/logs/ui
mkdir -p /config/backups

if [ ! -f /config/node/digibyte.conf ]; then
  cat > /config/node/digibyte.conf << 'EOF'
server=1
daemon=0
txindex=0
prune=550
rpcuser=dgb
rpcpassword=change_me
rpcallowip=127.0.0.1
rpcbind=127.0.0.1
printtoconsole=1
EOF
fi

if ! grep -q '^prune=' /config/node/digibyte.conf; then
  echo 'prune=550' >> /config/node/digibyte.conf
fi

if [ ! -f /config/ckpool/ckpool.conf ]; then
  cat > /config/ckpool/ckpool.conf << 'EOF'
{
  "name": "dgb-local",
  "coin": "dgb",
  "algo": "sha256d",
  "btcd": [
    {
      "url": "127.0.0.1:14022",
      "auth": "dgb",
      "pass": "change_me",
      "notify": true
    }
  ],
  "serverurl": [
    "0.0.0.0:3335"
  ],
  "startdiff": 42
}
EOF
fi

if [ ! -f /config/ui/settings.json ]; then
  cat > /config/ui/settings.json << 'EOF'
{
  "coin": "DGB",
  "algo": "sha256d",
  "label": "DGB Local Stack"
}
EOF
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf