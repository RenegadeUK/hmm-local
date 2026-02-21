FROM debian:bookworm-slim AS bitcoind-bins

ARG BTC_VERSION=28.0
ARG BTC_TARBALL_URL=https://bitcoincore.org/bin/bitcoin-core-${BTC_VERSION}/bitcoin-${BTC_VERSION}-x86_64-linux-gnu.tar.gz

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl tar && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN mkdir -p /out && \
    curl -fsSL "$BTC_TARBALL_URL" -o bitcoin.tar.gz && \
    tar -xzf bitcoin.tar.gz && \
    rm -f bitcoin.tar.gz && \
    btc_dir="$(ls -d bitcoin-* | head -n 1)" && \
    cp -f "/tmp/${btc_dir}/bin/bitcoind" /out/bitcoind && \
    cp -f "/tmp/${btc_dir}/bin/bitcoin-cli" /out/bitcoin-cli && \
    chmod +x /out/bitcoind /out/bitcoin-cli


FROM debian:bookworm-slim AS ckpool-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    yasm \
    autoconf \
    automake \
    libtool \
    pkgconf \
    libzmq3-dev \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY _ref_ckpool /src/ckpool
WORKDIR /src/ckpool
RUN find . -type f \( -name "*.sh" -o -name "*.ac" -o -name "*.am" -o -name "*.m4" \) -exec sed -i 's/\r$//' {} + && \
    sh ./autogen.sh && ./configure && make -j"$(nproc)"


FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends supervisor curl libzmq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ckpool-builder /src/ckpool/src/ckpool /usr/local/bin/ckpool
COPY --from=ckpool-builder /src/ckpool/src/ckpmsg /usr/local/bin/ckpmsg

COPY --from=bitcoind-bins /out/bitcoind /usr/bin/bitcoind
COPY --from=bitcoind-bins /out/bitcoin-cli /usr/bin/bitcoin-cli

COPY btc-stack/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY btc-stack/app ./app
COPY btc-stack/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY btc-stack/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8083 3333

ENTRYPOINT ["/entrypoint.sh"]