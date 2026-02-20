import os
import json
import logging
import base64
import re
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF
from openai import OpenAI

# ロギング設定
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

def sanitize_filename(filename):
    """ファイル名に使用できない文字を置換し、適切なファイル名に調整する"""
    if not filename:
        return ""
    invalid_chars = r'[\\/:*?"<>|]'
    sanitized = re.sub(invalid_chars, '_', filename)
    sanitized = sanitized.strip()
    return sanitized

class ObsidianOCREnhancer:
    def __init__(self, config):
        self.config = config
        self.client = OpenAI(base_url=config['common']['lm_studio_base_url'], api_key="lm-studio")
        self.temp_dir = Path(config['common'].get('temp_directory', 'temp_images'))
        if not self.temp_dir.exists():
            self.temp_dir.mkdir(parents=True)
        
        # 履歴ファイルのパス決定
        history_cfg = config['common'].get('history_file')
        script_dir = Path(__file__).parent.parent
        if history_cfg:
            self.history_path = script_dir / history_cfg
        else:
            self.history_path = script_dir / "data" / "history.json"

        self.history = self.load_history()

    def load_history(self):
        """履歴ファイルを読み込む。古い形式（パス:パス）もサポートする"""
        if self.history_path.exists():
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 互換性チェック: 全ての値が辞書形式か、古い文字列形式か
                    structured_data = {}
                    for key, value in data.items():
                        if isinstance(value, str):
                            structured_data[key] = {"md_path": value, "ocr_completed": False}
                        else:
                            structured_data[key] = value
                    return structured_data
            except Exception as e:
                logging.warning(f"Failed to load history: {e}")
        return {}

    def save_history(self):
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Failed to save history: {e}")

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def pdf_to_images(self, pdf_path):
        """PDFの全ページを一時的にPNG画像に変換する"""
        images = []
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_path = self.temp_dir / f"{Path(pdf_path).stem}_page_{i}.png"
                pix.save(str(img_path))
                images.append(img_path)
            doc.close()
        except Exception as e:
            logging.error(f"Error converting PDF to images: {e}")
        return images

    def get_page_ocr(self, image_path, page_num):
        """指定されたページの画像からOCRテキストを取得する"""
        try:
            prompt = self.config['ocr_enhancer']['fulltext_prompt'].format(page_number=page_num)
            base64_image = self.encode_image(image_path)
            
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                }
            ]

            response = self.client.chat.completions.create(
                model=self.config['common']['llm_model'],
                messages=[{"role": "user", "content": content}],
                temperature=0.2, # OCRの正確性を高めるため低めに設定
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error during OCR for page {page_num}: {e}")
            return f"### ページ {page_num}\n\n[[読み取り失敗: {e}]]"

    def enhance_markdown(self, md_path):
        """Markdownファイルを読み込み、PDFからOCR結果を追記する"""
        try:
            if not os.path.exists(md_path):
                logging.error(f"Markdown file not found: {md_path}")
                return False

            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 個別再処理フラグの確認
            reprocess_ocr_match = re.search(r'^reprocess_ocr:\s*true', content, re.MULTILINE | re.IGNORECASE)
            force_reprocess = bool(reprocess_ocr_match)

            # 既に全文OCRセクションがあるか、履歴で完了しているか確認（強制再処理でない場合）
            pdf_key = None # 後で取得
            
            if not force_reprocess:
                if "## 全文（OCR）" in content:
                    logging.info(f"Fulltext section already exists in {md_path}. Skipping.")
                    return True

            # フロントマターからソースPDFを取得
            # 従来の "パス" 形式と新しい "[[ファイル名]]" (Wiki Link) 形式の両方に対応
            source_match = re.search(r'^source:\s*"(.*?)"', content, re.MULTILINE)
            if not source_match:
                logging.warning(f"Source PDF info not found in frontmatter of {md_path}")
                return False
            
            raw_source = source_match.group(1)
            pdf_path = raw_source
            
            # Wikiリンク形式 [[filename.pdf]] の解析
            wiki_match = re.match(r'^\[\[(.*?)\]\]$', raw_source)
            if wiki_match:
                pdf_filename = wiki_match.group(1)
                # 設定されたPDF出力ディレクトリ内から検索
                pdf_base_dir = self.config.get('summarizer', {}).get('pdf_output', {}).get('destination_directory')
                if not pdf_base_dir:
                    logging.warning("PDF destination directory not configured. Cannot resolve Wiki Link.")
                    return False
                
                # 効率化のため、まずは直下やサブディレクトリを再帰的に探す
                found_path = None
                for root, dirs, files in os.walk(pdf_base_dir):
                    if pdf_filename in files:
                        found_path = os.path.join(root, pdf_filename)
                        break
                
                if found_path:
                    pdf_path = found_path
                else:
                    logging.warning(f"Could not find PDF file '{pdf_filename}' in {pdf_base_dir}")
                    return False

            pdf_key = str(Path(pdf_path).resolve()).replace('\\', '/')
            
            if not os.path.exists(pdf_path):
                logging.warning(f"Source PDF not found at {pdf_path}")
                return False

            # 履歴によるスキップ判定（強制再処理でない場合）
            if not force_reprocess and pdf_key in self.history:
                if self.history[pdf_key].get("ocr_completed"):
                    logging.info(f"OCR already completed for {pdf_path} (from history). Skipping.")
                    return True

            logging.info(f"Enhancing {md_path} with OCR from {pdf_path}")
            
            image_paths = []
            # 画像化
            image_paths = self.pdf_to_images(pdf_path)
            if not image_paths:
                return False
            # 各ページのOCR
            fulltext_parts = []
            max_pages = self.config['ocr_enhancer'].get('fulltext_max_pages', 50)
            
            for i, img_path in enumerate(image_paths):
                if i >= max_pages:
                    logging.info(f"Reached max pages limit ({max_pages}).")
                    fulltext_parts.append(f"\n\n> (注意: 設定により最大{max_pages}ページまでをOCR対象としています。)")
                    break
                
                logging.info(f"Processing page {i+1}/{len(image_paths)}...")
                page_text = self.get_page_ocr(img_path, i+1)
                fulltext_parts.append(page_text)

            # セクション構築
            header = (
                "\n---\n\n"
                "## 全文（OCR）\n\n"
                "> このセクションはAIにより画像から全文OCRされた内容です。\n"
                "> レイアウトの忠実再現ではなく、可読性と検索性を優先しています。\n\n"
            )
            fulltext_combined = header + "\n\n".join(fulltext_parts)

            # ファイルに追記（既存のセクションがあれば置換、なければ末尾に追加）
            if "## 全文（OCR）" in content:
                # 既存セクションを削除して新しい内容に差し替える
                new_content = re.sub(r'\n---\n\n## 全文（OCR）.*', fulltext_combined, content, flags=re.DOTALL)
            else:
                new_content = content + fulltext_combined

            # reprocess_ocr を false に書き戻す
            new_content = re.sub(r'^reprocess_ocr:\s*true', 'reprocess_ocr: false', new_content, flags=re.MULTILINE | re.IGNORECASE)

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # 履歴の更新
            self.history[pdf_key] = {
                "md_path": str(Path(md_path).resolve()).replace('\\', '/'),
                "ocr_completed": True
            }
            self.save_history()

            # 一時ファイルの削除
            for img_path in image_paths:
                try:
                    if img_path.exists():
                        img_path.unlink()
                except:
                    pass

            logging.info(f"Successfully enhanced {md_path}")
            return True

        except Exception as e:
            logging.error(f"Error enhancing {md_path}: {e}")
            return False

def main():
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / 'config' / 'config.json'
    if not config_path.exists():
        logging.error(f"Config file not found: {config_path}")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if not config['ocr_enhancer'].get('fulltext_enabled', True):
        logging.info("Fulltext OCR is disabled in config.")
        return

    enhancer = ObsidianOCREnhancer(config)

    # 出力ディレクトリ内のMarkdownファイルをスキャン
    output_dir = config['ocr_enhancer']['output_directory']
    if not os.path.exists(output_dir):
        logging.error(f"Output directory not found: {output_dir}")
        return

    processed_count = 0
    for root, dirs, files in os.walk(output_dir):
        for file_name in files:
            if file_name.lower().endswith('.md'):
                full_path = os.path.join(root, file_name)
                if enhancer.enhance_markdown(full_path):
                    processed_count += 1

    logging.info(f"OCR enhancement complete. {processed_count} files updated.")

if __name__ == "__main__":
    main()
