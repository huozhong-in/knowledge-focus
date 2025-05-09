# 判断/opt/postgresql_data 的文件夹是否存在，不存在则创建
if [ ! -d "/opt/postgresql_data" ]; then
    mkdir -p /opt/postgresql_data
fi
docker run -d \
    --name postgresql-pgvector-apacheage \
    --restart=unless-stopped \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=dswybs-yoqoo \
    -p 127.0.0.1:5432:5432 \
    -v "$PWD/postgresql.conf":/etc/postgresql/postgresql.conf \
    -v "$PWD/pg_hba.conf":/etc/postgresql/pg_hba.conf \
    -e PGDATA=/var/lib/postgresql/data/pgdata \
    -v /opt/postgresql_data:/var/lib/postgresql/data \
    -e TZ='Asia/Shanghai' \
    postgresql-pgvector-apacheage:latest