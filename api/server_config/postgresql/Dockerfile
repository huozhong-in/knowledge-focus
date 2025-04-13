ARG PG_MAJOR=16
FROM postgres:$PG_MAJOR
ARG PG_MAJOR

ENV http_proxy http://host.docker.internal:7890
ENV https_proxy http://host.docker.internal:7890

COPY pgvector /tmp/pgvector
COPY age /tmp/age

RUN export http_proxy=$http_proxy && \
    export https_proxy=$https_proxy && \
    apt-get update && \
    apt-get install -y --no-install-recommends build-essential postgresql-server-dev-$PG_MAJOR bison flex locales && \
    cd /tmp/pgvector && \
    make clean && \
    make OPTFLAGS="" && \
    make install && \
    mkdir /usr/share/doc/pgvector && \
    cp LICENSE README.md /usr/share/doc/pgvector && \
    cd ~ && \
    rm -rf /tmp/pgvector && \
    cd /tmp/age && \
    make && \
    make install && \
    cd ~ && \
    rm -rf /tmp/age && \
    apt-get remove -y build-essential postgresql-server-dev-$PG_MAJOR && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* && \
    echo "Cleanup completed successfully." && \
    echo "Dockerfile build completed successfully." && \
    echo "You can now run the container with the built image."
