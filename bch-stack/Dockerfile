FROM debian:bookworm-slim AS bchn-bins

ARG BCHN_VERSION=29.0.0
ARG BCHN_TARBALL_URL=https://github.com/bitcoin-cash-node/bitcoin-cash-node/releases/download/v${BCHN_VERSION}/bitcoin-cash-node-${BCHN_VERSION}-x86_64-linux-gnu.tar.gz

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl tar && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN mkdir -p /out && \
    curl -fsSL "$BCHN_TARBALL_URL" -o bchn.tar.gz && \
    tar -xzf bchn.tar.gz && \
    rm -f bchn.tar.gz && \
    bchn_dir="$(ls -d bitcoin-cash-node-* | head -n 1)" && \
    cp -f "/tmp/${bchn_dir}/bin/bitcoind" /out/bitcoind && \
    cp -f "/tmp/${bchn_dir}/bin/bitcoin-cli" /out/bitcoin-cli && \
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
    git \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 https://github.com/skaisser/ckpool.git /src/ckpool
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

COPY --from=bchn-bins /out/bitcoind /usr/bin/bitcoind
COPY --from=bchn-bins /out/bitcoin-cli /usr/bin/bitcoin-cli

COPY bch-stack/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bch-stack/app ./app
COPY bch-stack/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY bch-stack/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8084 3334

ENTRYPOINT ["/entrypoint.sh"]