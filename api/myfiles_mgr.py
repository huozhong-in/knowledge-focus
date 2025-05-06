from sqlmodel import (
    Session, 
    select, 
    asc, 
    desc, 
)
from datetime import datetime

class MyFilesManager:
    def __init__(self, session: Session) -> None:
        self.session = session


if __name__ == '__main__':
    pass