from config import TEST_DB_PATH
from models_api import get_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session
from sqlmodel import create_engine
session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
# 创建测试应用
app = FastAPI()

def get_test_session():
    return session

router = get_router(get_test_session)
app.include_router(router)

# 创建测试客户端
client = TestClient(app)

# 测试数据
test_data = {
    'messages': [
        {'role': 'user', 'content': 'Hello, what is the weather in Beijing?'}
    ],
    'session_id': 1
}

print('Testing agent-stream API endpoint:')
print('=' * 50)

# 发送POST请求
with client.stream('POST', '/chat/agent-stream', json=test_data) as response:
    print(f'Status Code: {response.status_code}')
    print(f'Headers: {dict(response.headers)}')
    print()
    print('Stream Content:')
    print('-' * 30)
    
    for chunk in response.iter_text():
        if chunk:
            print(chunk, end='')