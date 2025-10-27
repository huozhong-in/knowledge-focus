#!/usr/bin/env python3
"""
测试图片压缩功能
"""
import os
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import compress_image_to_binary


def test_compress_image():
    """测试图片压缩功能"""
    print("=" * 60)
    print("图片压缩功能测试")
    print("=" * 60)
    
    # 查找一个测试图片
    test_image = "dog.png"  # 使用api目录下的测试图片
    
    if not os.path.exists(test_image):
        print(f"❌ 测试图片不存在: {test_image}")
        print("请确保 api/dog.png 存在，或修改测试脚本指向其他图片")
        return
    
    print(f"\n测试图片: {test_image}")
    original_size = os.path.getsize(test_image)
    print(f"原始大小: {original_size / 1024:.2f} KB")
    
    try:
        # 测试压缩
        print("\n开始压缩...")
        compressed_data, mime_type = compress_image_to_binary(
            test_image,
            max_size=1920,
            quality=85
        )
        
        compressed_size = len(compressed_data)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        print(f"\n✅ 压缩成功!")
        print(f"压缩后大小: {compressed_size / 1024:.2f} KB")
        print(f"MIME类型: {mime_type}")
        print(f"压缩率: {compression_ratio:.1f}%")
        
        # 验证数据类型
        assert isinstance(compressed_data, bytes), "返回的数据应该是bytes类型"
        assert isinstance(mime_type, str), "MIME类型应该是字符串"
        assert mime_type == "image/jpeg", "压缩后应该是JPEG格式"
        
        print("\n✅ 所有断言通过!")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_compress_image()
