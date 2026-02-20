import os
import json
import logging
from pathlib import Path
from processors.pdf_processor import PDFProcessor
from processors.image_processor import ImageProcessor

# ロギング設定
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

def main():
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / 'config' / 'config.json'
    if not config_path.exists():
        logging.error(f"Config file not found: {config_path}")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    sum_config = config.get('summarizer', {})
    
    # 処理対象の設定をリストアップ
    # 旧形式（summarizer.input.directory 等）と新形式（summarizer.pdf, summarizer.jpeg）をサポート
    processing_targets = []

    # 1. 互換性のための旧形式チェック
    if 'input' in sum_config and 'directory' in sum_config['input']:
        old_input = sum_config['input']['directory']
        # 旧形式はPDFのみを対象としていたとみなす
        pdf_out = sum_config.get('pdf_output', {})
        processing_targets.append({
            "type": "pdf",
            "input_dir": old_input,
            "format_config": pdf_out
        })

    # 2. 新形式（PDF）
    if 'pdf' in sum_config:
        processing_targets.append({
            "type": "pdf",
            "input_dir": sum_config['pdf'].get('input_directory'),
            "format_config": sum_config['pdf']
        })

    # 3. 新形式（JPEG）
    if 'jpeg' in sum_config:
        processing_targets.append({
            "type": "jpeg",
            "input_dir": sum_config['jpeg'].get('input_directory'),
            "format_config": sum_config['jpeg']
        })

    # 重複排除（同じディレクトリを二度処理しないよう）
    seen_dirs = set()
    
    for target in processing_targets:
        input_base_dir = target["input_dir"]
        if not input_base_dir or not os.path.exists(input_base_dir):
            continue
        
        target_key = (target["type"], str(Path(input_base_dir).resolve()))
        if target_key in seen_dirs:
            continue
        seen_dirs.add(target_key)

        logging.info(f"Scanning directory for {target['type']}: {input_base_dir}")
        
        if target["type"] == "pdf":
            processor = PDFProcessor(config, target["format_config"])
            extensions = ('.pdf',)
        elif target["type"] == "jpeg":
            processor = ImageProcessor(config, target["format_config"])
            extensions = ('.jpg', '.jpeg')
        else:
            continue

        processed_count = 0
        for root, dirs, files in os.walk(input_base_dir):
            relative_dir = os.path.relpath(root, input_base_dir)
            if relative_dir == ".":
                relative_dir = ""
                
            target_files = [f for f in files if f.lower().endswith(extensions)]
            
            for file_name in target_files:
                full_path = os.path.join(root, file_name)
                processor.process(full_path, relative_dir)
                processed_count += 1

        logging.info(f"Finished processing {target['type']}: {processed_count} files found.")

if __name__ == "__main__":
    main()
