import os
import logging
import re
import json
from pathlib import Path
from .base_processor import BaseProcessor

class ImageProcessor(BaseProcessor):
    def process(self, image_path, relative_dir=""):
        img_key = str(Path(image_path).resolve()).replace('\\', '/')
        
        if img_key in self.history:
            entry = self.history[img_key]
            md_path_str = entry["md_path"]
            if not self.should_reprocess(md_path_str):
                logging.info(f"Skipping: {image_path} (Already exists at {md_path_str})")
                return
            else:
                logging.info(f"Reprocessing: {image_path}")

        logging.info(f"Processing Image: {image_path}")
        
        try:
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

            modified_prompt = f"{classifier_info}\n\n{base_prompt}"
            ai_response = self.get_ai_summary([Path(image_path)], custom_prompt=modified_prompt)
            
            ai_data = self._parse_ai_response(ai_response, Path(image_path).stem)

            md_path, copy_path, category = self.get_output_paths(ai_data, image_path, relative_dir)
            
            final_file_name = Path(copy_path).name if copy_path else Path(image_path).name

            # 保存
            self.generate_markdown(md_path, ai_data, ai_response, category, final_file_name)

            logging.info(f"Markdown generated: {md_path}")

            final_img_key = str(Path(image_path).resolve()).replace('\\', '/')
            self.history[final_img_key] = {
                "md_path": str(Path(md_path).resolve()).replace('\\', '/'),
                "ocr_completed": False
            }
            self.save_history()

            if copy_path:
                import shutil
                shutil.copy2(image_path, copy_path)
                logging.info(f"Image copied to: {copy_path}")

        except Exception as e:
            logging.error(f"Error processing {image_path}: {e}")

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
