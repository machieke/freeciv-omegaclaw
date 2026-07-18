FROM ubuntu:noble AS build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates libbz2-dev libcurl4-openssl-dev libicu-dev \
    libjansson-dev liblzma-dev libsqlite3-dev libtool libzstd-dev meson ninja-build \
    pkgconf python3 zlib1g-dev && rm -rf /var/lib/apt/lists/*

COPY source /src
RUN meson setup /build /src \
      --prefix=/opt/freeciv \
      -Dclients=[] -Dfcmp=[] -Druledit=false -Daudio=false -Dmwand=false \
      -Dnls=false -Dreadline=false -Dserver=enabled -Dbuildtype=release && \
    meson compile -C /build freeciv-research-parity

FROM ubuntu:noble
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4t64 libicu74 libjansson4 liblzma5 libsqlite3-0 libzstd1 zlib1g && \
    rm -rf /var/lib/apt/lists/*
COPY --from=build /build/freeciv-research-parity /usr/local/bin/freeciv-research-parity
COPY --from=build /build/libfreeciv.so /usr/local/lib/libfreeciv.so
COPY --from=build /src/data /opt/freeciv/share/freeciv
ENV FREECIV_DATA_PATH=/opt/freeciv/share/freeciv
ENV LD_LIBRARY_PATH=/usr/local/lib
ENTRYPOINT ["/usr/local/bin/freeciv-research-parity"]
