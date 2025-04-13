from fastapi import FastAPI
import uvicorn
import argparse
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="API服务监听端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
    args = parser.parse_args()
    
    print(f"API服务启动在: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)