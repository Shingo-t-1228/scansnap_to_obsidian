import os
import logging
import fitz  # PyMuPDF
import re
import json
from pathlib import Path
from .base_processor import BaseProcessor

class PDFProcessor(BaseProcessor):
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

    def process(self, pdf_path, relative_dir=""):
        pdf_key = str(Path(pdf_path).resolve()).replace('\\', '/')
        
        if pdf_key in self.history:
            entry = self.history[pdf_key]
            md_path_str = entry["md_path"]
            if not self.should_reprocess(md_path_str):
                logging.info(f"Skipping: {pdf_path} (Already exists at {md_path_str})")
                return
            else:
                logging.info(f"Reprocessing: {pdf_path}")

        logging.info(f"Processing PDF: {pdf_path}")
        
        image_paths = []
        try:
            image_paths = self.pdf_to_images(pdf_path)
            if not image_paths:
                logging.error("No images generated from PDF.")
                return

            total_pages = len(image_paths)
            max_pages = self.config.get('summarizer', {}).get('ai_analysis', {}).get('max_pages_to_ai', 5)
            
            ai_image_paths = image_paths
            sampling_info = ""
            
            if total_pages > max_pages:
                first_part = image_paths[:max_pages - 1]
                last_page = [image_paths[-1]]
                ai_image_paths = first_part + last_page
                sampled_indices = [i + 1 for i in range(max_pages - 1)] + [total_pages]
                sampling_info = f"\n\n(注意: この書類は全{total_pages}ページありますが、現在はコンテキスト節約のため、{', '.join(map(str, sampled_indices))}ページ目のみを抜粋して送信しています。)"
                logging.info(f"Sampling applied: sending {len(ai_image_paths)}/{total_pages} pages.")

            base_prompt = self.config.get('summarizer', {}).get('ai_analysis', {}).get('prompt')
            classifier_info = ""
            if 'classification_rules' in self.config.get('summarizer', {}).get('ai_analysis', {}):
                rules = self.config['summarizer']['ai_analysis']['classification_rules']
                rules_text = "\n".join([f"- {r['name']}: {r.get('description', '')}" for r in rules])
                classifier_info = (
                    f"\n\n### 分類ルールと判定基準\n"
                    f"以下のカテゴリ名から、書類の内容に最も合致するものを1つだけ選択してください。\n"
                    f"選択肢:\n{rules_text}\n"
                )

            modified_prompt = f"{sampling_info}{classifier_info}\n\n{base_prompt}"
            ai_response = self.get_ai_summary(ai_image_paths, custom_prompt=modified_prompt)
            
            # AI応答のパース
            ai_data = self._parse_ai_response(ai_response, Path(pdf_path).stem)

            # 出力先決定
            md_path, copy_path, category = self.get_output_paths(ai_data, pdf_path, relative_dir)
            
            # 最終的なファイル名の取得（リンク用）
            final_file_name = Path(copy_path).name if copy_path else Path(pdf_path).name

            # Markdown生成
            self.generate_markdown(md_path, ai_data, ai_response, category, final_file_name)

            logging.info(f"Markdown generated: {md_path}")

            # 履歴更新
            final_pdf_key = str(Path(pdf_path).resolve()).replace('\\', '/')
            self.history[final_pdf_key] = {
                "md_path": str(Path(md_path).resolve()).replace('\\', '/'),
                "ocr_completed": False
            }
            self.save_history()

            # PDFコピー
            if copy_path:
                import shutil
                shutil.copy2(pdf_path, copy_path)
                logging.info(f"PDF copied to: {copy_path}")

        except Exception as e:
            logging.error(f"Error processing {pdf_path}: {e}")
        finally:
            if not self.config['common'].get('keep_temp_files', False):
                for img_path in image_paths:
                    if img_path.exists():
                        img_path.unlink()

    def _parse_ai_response(self, ai_response, default_title):
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', ai_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            else:
                json_str = ai_response.strip()
                if json_str.startswith("```"):
                    json_str = re.sub(r'^```[a-z]*\n', '', json_str)
                    json_str = re.sub(r'\n```$', '', json_str)
                return json.loads(json_str)
        except:
            return {
                "title": default_title,
                "category": "99_未分類",
                "author": "Unknown",
                "published": "Unknown",
                "description": "",
                "tags": [],
                "summary": ai_response
            }
