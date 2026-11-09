import os
import csv
from PIL import Image
from pyzbar.pyzbar import decode
from core.qr_generator import generate

def run_tests():
    # 创建输出目录
    os.makedirs("outputs/qr_test", exist_ok=True)
    os.makedirs("outputs/qr_test/failures", exist_ok=True)
    
    # 1. 加载你刚放进来的猫图
    cat_path = "test_cat.png"
    cat_img = None
    if os.path.exists(cat_path):
        cat_img = Image.open(cat_path)
        print(f"成功加载猫图: {cat_path}")
    else:
        print(f"⚠️ 警告：找不到 {cat_path}，将生成纯二维码。请把猫图放到根目录。")

    # 2. 正常案例列表
    cases = [
        {"name": "case_1_H_level_with_cat", "text": "https://example.com/hello", "config": {"correction": "H", "cat_image": cat_img}},
        {"name": "case_2_Q_level_pure_qr", "text": "https://example.com/world", "config": {"correction": "Q"}},
    ]
    
    results = []
    
    for case in cases:
        # 调用你的生成算法
        res = generate(case["text"], case["config"])
        path = f"outputs/qr_test/{case['name']}.png"
        # 保存生成的图片
        res["image"].save(path)
        
        # 用 pyzbar 自动扫码
        decoded = decode(Image.open(path))
        text = decoded[0].data.decode("utf-8") if decoded else None
        success = (text == case["text"])
        
        results.append({
            "case_name": case["name"],
            "expected_text": case["text"],
            "decoded_text": text,
            "scan_success": success,
            "correction": res["correction"],
            "qr_version": res["qr_version"]
        })
        print(f"测试 {case['name']} 扫码结果: {success}")

    # 3. 故意制造失败案例
    print("--- 正在制造失败样例 ---")
    try:
        generate("", {})
    except ValueError as e:
        with open("outputs/qr_test/failures/error_log.txt", "w", encoding="utf-8") as f:
            f.write(f"预期失败测试（空文本）: {str(e)}\n")
    
    # 4. 写入 CSV
    with open("outputs/qr_test/scan_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_name", "expected_text", "decoded_text", "scan_success", "correction", "qr_version"])
        writer.writeheader()
        writer.writerows(results)

if __name__ == "__main__":
    run_tests()