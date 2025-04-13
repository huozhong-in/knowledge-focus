# 判断postgresql_data的volume是否存在，不存在则创建
if [ ! "$(docker volume ls -q -f name=postgresql_data)" ]; then
    docker volume create postgresql_data
fi
# 从.env文件中读取环境变量POSTGRES_USER和POSTGRES_PASSWORD
export $(grep -v '^#' .env | xargs)
docker run -d \
    --name postgresql-pgvector-apacheage \
    --restart=unless-stopped \
    -e POSTGRES_USER=$POSTGRES_USER \
    -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
    -p 127.0.0.1:65432:5432 \
    -v "$PWD/postgresql.conf":/etc/postgresql/postgresql.conf \
    -v "$PWD/pg_hba.conf":/etc/postgresql/pg_hba.conf \
    -e PGDATA=/var/lib/postgresql/data/pgdata \
	-v postgresql_data:/var/lib/postgresql/data \
    -e TZ='Asia/Shanghai' \
    postgresql-pgvector-apacheage:latest
