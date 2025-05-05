from sqlmodel import Field, SQLModel, Session, select, inspect, text

# 表结构设计
class Settings(SQLModel, table=True):
    __tablename__ = "t_settings"
    id: int = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: str
    description: str | None = None


class DBManager:
    """数据库管理类，负责直接操作各业务模块数据表，从上层拿到session，自己不管理数据库连接"""
    
    def __init__(self, session: Session) -> None:
        self.session = session
        

    def init_db(self) -> bool:
        """初始化数据库"""
        engine = self.session.get_bind()
        inspector = inspect(engine)

        # 创建表
        with engine.connect() as conn:
            if not inspector.has_table(Settings.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Settings.__table__])
                # 适当增加索引
                # if not any([col['name'] == 'idx_talker_id' for col in inspector.get_indexes(Settings.__tablename__)]):
                #     conn.execute(text(f'CREATE INDEX idx_talker_id ON {Settings.__tablename__} (id);'))
        
        return True
    
if __name__ == '__main__':
    db_mgr = DBManager(Session())
    db_mgr.init_db()
    print("数据库初始化完成")