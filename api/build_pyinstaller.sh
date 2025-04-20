pyinstaller -y --target-architecture arm64 --osx-bundle-identifier knowledge-focus.huozhong.in --collect-all uvicorn --collect-all argparse --collect-all fastapi -F -n kf-api main.py
