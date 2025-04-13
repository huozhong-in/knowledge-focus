# 如果postgresql-pgvector-apacheage:latest不存在，需要先build镜像
if [ "$(docker images -q postgresql-pgvector-apacheage:latest 2> /dev/null)" == "" ]; then
    git clone https://github.com/pgvector/pgvector.git
    git clone https://github.com/apache/age.git
    docker build -t postgresql-pgvector-apacheage:latest .
    rm -rf pgvector
    rm -rf age
else
    echo "postgresql-pgvector-apacheage:latest already exists"
    exit 0
fi
