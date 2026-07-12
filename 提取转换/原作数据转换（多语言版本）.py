import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import re
import json
import os
import threading
from queue import Queue
import gc
from collections import Counter

class GalgameScriptConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Galgame剧本转换器 - 章节修复版（含s字段）")
        self.root.geometry("1000x750")
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text = tk.StringVar(value="就绪")
        self.is_processing = False
        self.cancel_processing = False
        self.queue = Queue()
        self.scene_meta_by_start = {}
        
        self.setup_ui()
        self.check_queue()
    
    # ---------- UI 界面 ----------
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(control_frame, text="ID起始（固定1）:").grid(row=0, column=0, sticky=tk.W, padx=(0,5))
        self.id_start_var = tk.StringVar(value="1")
        ttk.Entry(control_frame, textvariable=self.id_start_var, width=10, state="readonly").grid(row=0, column=1, sticky=tk.W, padx=(0,10))
        
        ttk.Button(control_frame, text="转换", command=self.start_conversion).grid(row=0, column=2, padx=5)
        self.cancel_button = ttk.Button(control_frame, text="取消", command=self.cancel_processing_func, state=tk.DISABLED)
        self.cancel_button.grid(row=0, column=3, padx=5)
        
        ttk.Button(control_frame, text="导入JSON文件", command=self.import_json_files).grid(row=0, column=4, padx=5)
        ttk.Button(control_frame, text="导出TXT", command=self.export_txt).grid(row=0, column=5, padx=5)
        ttk.Button(control_frame, text="导出流程图", command=self.export_flowchart).grid(row=0, column=6, padx=5)
        ttk.Button(control_frame, text="清除", command=self.clear_all).grid(row=0, column=7, padx=5)
        ttk.Button(control_frame, text="加载示例", command=self.load_example).grid(row=0, column=8, padx=5)
        
        self.merge_var = tk.IntVar(value=1)
        ttk.Checkbutton(control_frame, text="合并导入的文件（自动偏移ID）", variable=self.merge_var).grid(row=0, column=9, padx=10)
        
        self.file_info_var = tk.StringVar(value="未选择文件")
        ttk.Label(control_frame, textvariable=self.file_info_var, foreground="blue").grid(row=0, column=10, padx=20)
        
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0,10))
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_text)
        self.progress_label.grid(row=0, column=0, sticky=tk.W)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5,0))
        
        ttk.Label(main_frame, text="原始剧本格式 (scenes JSON):").grid(row=2, column=0, sticky=tk.W, pady=(0,5))
        ttk.Label(main_frame, text="转换后格式 (JSON):").grid(row=2, column=1, sticky=tk.W, pady=(0,5))
        
        self.input_text = scrolledtext.ScrolledText(main_frame, height=25, width=50, wrap=tk.WORD)
        self.input_text.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0,10))
        self.output_text = scrolledtext.ScrolledText(main_frame, height=25, width=50, wrap=tk.WORD)
        self.output_text.grid(row=3, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN).grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10,0))
        
        self.imported_files = []
        self._bind_mouse_wheel()
    
    def _bind_mouse_wheel(self):
        def on_wheel(event, widget):
            widget.yview_scroll(int(-1*(event.delta/120)), "units")
        self.input_text.bind("<MouseWheel>", lambda e: on_wheel(e, self.input_text))
        self.output_text.bind("<MouseWheel>", lambda e: on_wheel(e, self.output_text))
        self.input_text.bind("<Button-4>", lambda e: self.input_text.yview_scroll(-1, "units"))
        self.input_text.bind("<Button-5>", lambda e: self.input_text.yview_scroll(1, "units"))
        self.output_text.bind("<Button-4>", lambda e: self.output_text.yview_scroll(-1, "units"))
        self.output_text.bind("<Button-5>", lambda e: self.output_text.yview_scroll(1, "units"))
    
    def check_queue(self):
        try:
            while not self.queue.empty():
                msg_type, data = self.queue.get_nowait()
                if msg_type == "progress_update":
                    self.progress_var.set(data["progress"])
                    self.progress_text.set(data["message"])
                elif msg_type == "status_update":
                    self.status_var.set(data)
                elif msg_type == "file_info":
                    self.file_info_var.set(data)
                elif msg_type == "output_text":
                    self.output_text.delete("1.0", tk.END)
                    self.output_text.insert("1.0", data)
                elif msg_type == "input_text":
                    self.input_text.delete("1.0", tk.END)
                    self.input_text.insert("1.0", data)
                elif msg_type == "processing_done":
                    self.is_processing = False
                    self.cancel_processing = False
                    self.cancel_button.config(state=tk.DISABLED)
                    self.progress_text.set("完成")
                elif msg_type == "processing_error":
                    self.is_processing = False
                    self.cancel_processing = False
                    self.cancel_button.config(state=tk.DISABLED)
                    self.progress_text.set("出错")
                    messagebox.showerror("错误", data)
        except Exception as e:
            print(f"队列错误: {e}")
        self.root.after(100, self.check_queue)
    
    def start_conversion(self):
        if self.is_processing:
            return
        self.is_processing = True
        self.cancel_processing = False
        self.cancel_button.config(state=tk.NORMAL)
        threading.Thread(target=self.convert_script_thread, daemon=True).start()
    
    def cancel_processing_func(self):
        self.cancel_processing = True
        self.status_var.set("正在取消...")
    
    def import_json_files(self):
        if self.is_processing:
            messagebox.showwarning("警告", "正在处理中")
            return
        files = filedialog.askopenfilenames(
            title="选择JSON文件",
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not files:
            return
        self.is_processing = True
        self.cancel_processing = False
        self.cancel_button.config(state=tk.NORMAL)
        threading.Thread(target=self._process_files_import, args=(files,), daemon=True).start()
    
    def _process_files_import(self, files):
        try:
            self.queue.put(("status_update", f"导入 {len(files)} 个文件..."))
            self.imported_files = list(files)
            all_content = ""
            for fp in files:
                if self.cancel_processing:
                    break
                with open(fp, 'r', encoding='utf-8-sig') as f:
                    all_content += f"\n{'='*60}\n文件: {os.path.basename(fp)}\n{'='*60}\n" + f.read()
                gc.collect()
            self.queue.put(("input_text", all_content))
            self.queue.put(("file_info", f"已导入 {len(files)} 个文件"))
            self.queue.put(("status_update", "导入完成"))
        except Exception as e:
            self.queue.put(("processing_error", f"导入错误: {e}"))
        finally:
            self.queue.put(("processing_done", None))
    
    def export_txt(self):
        output_text = self.output_text.get("1.0", tk.END).strip()
        if not output_text:
            messagebox.showwarning("警告", "没有可导出的内容")
            return
        save_dir = filedialog.askdirectory(title="选择保存目录")
        if not save_dir:
            return
        try:
            data = json.loads(output_text)
            if not isinstance(data, dict):
                raise ValueError("不是JSON对象")
            main_data = {k: v for k, v in data.items() if not k.startswith("_")}
            items = sorted(main_data.items(), key=lambda x: int(x[0]))
            total = len(items)
            chunk_size = 500
            for i in range(0, total, chunk_size):
                chunk = dict(items[i:i+chunk_size])
                fname = f"scriptData{i//chunk_size+1}.txt"
                with open(os.path.join(save_dir, fname), 'w', encoding='utf-8') as f:
                    json.dump(chunk, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("完成", f"导出 {total} 条对话到 {save_dir}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")
    
    def export_flowchart(self):
        output_text = self.output_text.get("1.0", tk.END).strip()
        if not output_text:
            messagebox.showwarning("警告", "没有可导出的内容")
            return
        try:
            data = json.loads(output_text)
            if not isinstance(data, dict):
                raise ValueError("不是JSON对象")
            
            flowchart_lines = []
            for key, val in data.items():
                if val.get("co"):
                    targets = []
                    branch_nexts = []
                    opt_count = 0
                    for opt_idx in range(1, 6):
                        t_key = f"c{opt_idx}t"
                        if t_key in val and val[t_key] > 0:
                            opt_count += 1
                            target_id = val[t_key]
                            branch_end = target_id
                            next_ids = []
                            if self.scene_meta_by_start:
                                for start, (end, nids) in self.scene_meta_by_start.items():
                                    if start <= target_id <= end:
                                        branch_end = end
                                        next_ids = nids
                                        break
                            targets.append(f"{target_id} -> {branch_end}")
                            if next_ids:
                                branch_nexts.extend(next_ids)
                    if targets:
                        line = f"{key}: {', '.join(targets)}"
                        common_merge = None
                        if branch_nexts and opt_count > 0:
                            cnt = Counter(branch_nexts)
                            for nid, count in cnt.items():
                                if count == opt_count:
                                    common_merge = nid
                                    break
                        if common_merge is not None:
                            line += f" 合流：{common_merge}"
                        flowchart_lines.append(line)
            
            if not flowchart_lines:
                messagebox.showinfo("提示", "未找到任何选项条目")
                return
            
            save_path = filedialog.asksaveasfilename(
                title="保存流程图",
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            if not save_path:
                return
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(flowchart_lines))
            messagebox.showinfo("完成", f"流程图已保存到 {save_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出流程图失败: {e}")
    
    def clear_all(self):
        self.input_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)
        self.imported_files = []
        self.file_info_var.set("未选择文件")
        self.status_var.set("已清除")
        self.progress_var.set(0)
        self.progress_text.set("就绪")
        self.scene_meta_by_start = {}
    
    # ---------- 工具函数 ----------
    def clean_text(self, text):
        if not text:
            return ""
        text = text.replace("\\n", "\n")
        for ch in ["%n", "；", "\\t", "\\r"]:
            text = text.replace(ch, "")
        return text.strip()
    
    def format_speaker(self, name):
        if not name:
            return ""
        if "【" not in name and "】" not in name:
            return f"【{name}】"
        return name
    
    # ---------- 背景/立绘/CG/SD提取 ----------
    def _extract_background_from_data(self, data_arr):
        for item in data_arr:
            if isinstance(item, list) and len(item) >= 3 and item[1] == "stage":
                params = item[2]
                if isinstance(params, dict):
                    redraw = params.get("redraw", {})
                    img = redraw.get("imageFile", {})
                    if isinstance(img, dict):
                        file = img.get("file", "")
                        if isinstance(file, str) and file:
                            if '.' in file:
                                file = file.rsplit('.', 1)[0]
                            has_blur = self._check_doBoxBlur(img)
                            return file, has_blur
        return "", False

    def _extract_characters_from_data(self, data_arr):
        chars = []
        for item in data_arr:
            if isinstance(item, list) and len(item) >= 3 and item[1] == "character":
                params = item[2]
                if isinstance(params, dict) and params.get("showmode") == 3:
                    redraw = params.get("redraw", {})
                    img = redraw.get("imageFile", {})
                    if isinstance(img, dict):
                        file = img.get("file", "")
                        if isinstance(file, str) and file:
                            opts = img.get("options", {})
                            dress = opts.get("dress", "")
                            pose = opts.get("pose", "")
                            parts = []
                            if dress:
                                parts.append(f"dress={dress}")
                            if pose:
                                parts.append(f"pose={pose}")
                            query = "&".join(parts)
                            chars.append(f"{file}?{query}" if query else file)
        return ";".join(chars)

    def _extract_cg_from_data(self, data_arr):
        cgs = []
        for item in data_arr:
            if isinstance(item, list) and len(item) >= 3 and item[1] in ("event", "centerlayer"):
                params = item[2]
                if isinstance(params, dict):
                    if item[1] == "centerlayer" and params.get("showmode") != 3:
                        continue
                    img = params.get("redraw", {}).get("imageFile", {})
                    if isinstance(img, dict):
                        file = img.get("file", "")
                        if isinstance(file, str) and file:
                            if '.' in file:
                                file = file.rsplit('.', 1)[0]
                            cgs.append(file)
        return ";".join(cgs)
    
    def _extract_sd_from_data(self, data_arr):
        sds = []
        for item in data_arr:
            if isinstance(item, list) and len(item) >= 3 and item[1] == "sdlayer":
                params = item[2]
                if isinstance(params, dict):
                    img = params.get("redraw", {}).get("imageFile", {})
                    if isinstance(img, dict):
                        file = img.get("file", "")
                        if isinstance(file, str) and file:
                            if '.' in file:
                                file = file.rsplit('.', 1)[0]
                            sds.append(file)
        return ";".join(sds)

    def _check_doBoxBlur(self, obj):
        if isinstance(obj, dict):
            return any(self._check_doBoxBlur(v) for v in obj.values())
        elif isinstance(obj, list):
            return any(self._check_doBoxBlur(x) for x in obj)
        elif isinstance(obj, str) and "doBoxBlur" in obj:
            return True
        return False

    # ---------- 对话条目转换 ----------
    def entry_to_dict(self, entry):
        if not isinstance(entry, list) or len(entry) < 2:
            return None

        text_list = entry[2] if len(entry) > 2 and isinstance(entry[2], list) else None
        if text_list and len(text_list) > 0:
            chinese_idx = 2 if len(text_list) > 2 else (1 if len(text_list) > 1 else 0)
            chinese_entry = text_list[chinese_idx] if chinese_idx < len(text_list) else None
            if isinstance(chinese_entry, list) and len(chinese_entry) >= 2:
                text = self.clean_text(chinese_entry[1]) if isinstance(chinese_entry[1], str) else ""
                if text:
                    speaker_inner = chinese_entry[0] if isinstance(chinese_entry[0], str) else None
                    speaker = speaker_inner if speaker_inner else (entry[0] if isinstance(entry[0], str) else "")
                    speaker = self.format_speaker(speaker)
                    bg, blur, chars, cg, sd = "", False, "", "", ""
                    if len(entry) > 5 and isinstance(entry[5], dict):
                        data_arr = entry[5].get("data", [])
                        if isinstance(data_arr, list):
                            bg, blur = self._extract_background_from_data(data_arr)
                            chars = self._extract_characters_from_data(data_arr)
                            cg = self._extract_cg_from_data(data_arr)
                            sd = self._extract_sd_from_data(data_arr)
                    return {
                        "speaker_raw": speaker.strip("【】") if speaker else "",
                        "speaker": speaker,
                        "text": text,
                        "background": bg,
                        "blur": blur,
                        "characters": chars,
                        "cg": cg,
                        "sd": sd
                    }

        old_text_list = entry[1] if len(entry) > 1 and isinstance(entry[1], list) else None
        if old_text_list and len(old_text_list) > 0:
            first = old_text_list[0]
            if isinstance(first, list) and len(first) >= 2:
                text = self.clean_text(first[1]) if isinstance(first[1], str) else ""
                if text:
                    speaker = entry[0] if isinstance(entry[0], str) else ""
                    speaker = self.format_speaker(speaker)
                    return {
                        "speaker_raw": speaker.strip("【】") if speaker else "",
                        "speaker": speaker,
                        "text": text,
                        "background": "",
                        "blur": False,
                        "characters": "",
                        "cg": "",
                        "sd": ""
                    }
        return None

    # ---------- 核心解析：提取对话、选项、章节，建立标签映射 ----------
    def parse_script_with_options(self, input_data):
        if input_data.startswith('\ufeff'):
            input_data = input_data[1:]

        try:
            parsed = json.loads(input_data)
        except:
            return [], {}, {}

        if not isinstance(parsed, dict) or "scenes" not in parsed:
            return [], {}, {}

        entries = []
        label_to_id = {}
        scene_meta = {}
        current_id = 1

        for scene in parsed["scenes"]:
            label = scene.get("label", "")
            scene_start = current_id

            # ====== 提取 chapter 行 ======
            lines = scene.get("lines", [])
            chapter_str = None
            for line in lines:
                if isinstance(line, list) and len(line) >= 2 and line[0] == "chapter":
                    chapter_str = line[1]
                    break
            if chapter_str:
                chapter_entry = {
                    "speaker_raw": f"[CHAPTER{chapter_str}]",
                    "speaker": f"[CHAPTER{chapter_str}]",
                    "text": "",
                    "background": "ecall",
                    "blur": False,
                    "characters": "",
                    "cg": "",
                    "sd": "",
                    "is_chapter": True
                }
                entries.append(chapter_entry)
                if label and label not in label_to_id:
                    label_to_id[label] = current_id
                current_id += 1

            # 提取对话
            for text_item in scene.get("texts", []):
                if self.cancel_processing:
                    break
                if not isinstance(text_item, list):
                    continue
                d = self.entry_to_dict(text_item)
                if d:
                    entries.append(d)
                    if label and label not in label_to_id:
                        label_to_id[label] = current_id
                    current_id += 1

            # 提取选项
            selects = scene.get("selects", [])
            if selects:
                opt_entry = {
                    "co": True,
                    "c1": "", "c1t": "",
                    "c2": "", "c2t": "",
                    "c3": "", "c3t": "",
                    "c4": "", "c4t": "",
                    "c5": "", "c5t": ""
                }
                if label and label not in label_to_id and scene_start == current_id:
                    label_to_id[label] = current_id

                for idx, sel in enumerate(selects[:5]):
                    lang = sel.get("language", [])
                    text = ""
                    if len(lang) > 2 and isinstance(lang[2], dict):
                        text = lang[2].get("text", "")
                    elif len(lang) > 1 and isinstance(lang[1], dict):
                        text = lang[1].get("text", "")
                    else:
                        text = sel.get("text", "")
                    target_label = sel.get("target", "")
                    if idx == 0:
                        opt_entry["c1"] = text
                        opt_entry["c1t"] = target_label
                    elif idx == 1:
                        opt_entry["c2"] = text
                        opt_entry["c2t"] = target_label
                    elif idx == 2:
                        opt_entry["c3"] = text
                        opt_entry["c3t"] = target_label
                    elif idx == 3:
                        opt_entry["c4"] = text
                        opt_entry["c4t"] = target_label
                    elif idx == 4:
                        opt_entry["c5"] = text
                        opt_entry["c5t"] = target_label
                entries.append(opt_entry)
                if label and label not in label_to_id:
                    label_to_id[label] = current_id
                current_id += 1

            if label and label not in label_to_id:
                label_to_id[label] = current_id

            scene_end = current_id - 1 if current_id > scene_start else scene_start - 1
            if scene_end >= scene_start:
                next_targets = []
                for nxt in scene.get("nexts", []):
                    if isinstance(nxt, dict) and "target" in nxt:
                        next_targets.append(nxt["target"])
                scene_meta[label] = {"start": scene_start, "end": scene_end, "nexts": next_targets}

        return entries, label_to_id, scene_meta

    # ---------- 立绘处理 ----------
    def process_characters(self, entries):
        def get_raw(s):
            m = re.search(r'【(.+?)】', s)
            return m.group(1) if m else s.strip()
        def unique(s):
            return ';'.join(dict.fromkeys(s.split(';'))) if s else s
        
        is_ref = [False] * len(entries)
        for i, item in enumerate(entries):
            if item.get("is_chapter"):
                continue
            sp = item.get("speaker", "")
            ch = item.get("characters", "")
            if not sp or not ch:
                continue
            poses = ch.split(';')
            ori_len = len(poses)
            poses = list(dict.fromkeys(poses))
            raw = get_raw(sp)
            matched = [p for p in poses if p.startswith(raw + '.')]
            if matched:
                item["characters"] = matched[0]
                if ori_len > 1:
                    is_ref[i] = True
            else:
                item["characters"] = ';'.join(poses)
        for i, item in enumerate(entries):
            if is_ref[i] or item.get("is_chapter"):
                continue
            ch = item.get("characters", "")
            if not ch:
                continue
            poses = list(dict.fromkeys(ch.split(';')))
            if len(poses) <= 1:
                item["characters"] = ';'.join(poses)
                continue
            raw = get_raw(item.get("speaker", ""))
            ref_idx = None
            for j in range(i-1, -1, -1):
                if is_ref[j]:
                    ref_idx = j
                    break
            if ref_idx is not None:
                ref_raw = get_raw(entries[ref_idx].get("speaker", ""))
                matched = [p for p in poses if p.startswith(ref_raw + '.')]
                item["characters"] = matched[0] if matched else poses[0]
            else:
                item["characters"] = poses[0]
        for item in entries:
            if "characters" in item and item["characters"] and not item.get("is_chapter"):
                item["characters"] = unique(item["characters"])

    # ---------- 去重相邻选项 ----------
    def deduplicate_adjacent_option_pages(self, entries):
        if not entries:
            return entries

        delete_indices = set()
        i = 0
        while i < len(entries) - 1:
            if entries[i].get("co") and entries[i+1].get("co"):
                def get_option_key(entry):
                    key_parts = []
                    for idx in range(1, 6):
                        text = entry.get(f"c{idx}", "")
                        target = entry.get(f"c{idx}t", 0)
                        key_parts.append(f"{text}|{target}")
                    return "||".join(key_parts)
                if get_option_key(entries[i]) == get_option_key(entries[i+1]):
                    delete_indices.add(i+1)
                    i += 2
                else:
                    i += 1
            else:
                i += 1

        if not delete_indices:
            return entries

        new_entries = []
        for idx, entry in enumerate(entries):
            if idx not in delete_indices:
                new_entries.append(entry)

        del_ids = sorted([idx+1 for idx in delete_indices])
        for entry in new_entries:
            if entry.get("co"):
                for opt_key in ["c1t", "c2t", "c3t", "c4t", "c5t"]:
                    target = entry.get(opt_key, 0)
                    if target > 0:
                        new_target = target
                        for d in del_ids:
                            if d < target:
                                new_target -= 1
                            elif d == target:
                                new_target = 0
                                break
                        entry[opt_key] = new_target
        return new_entries

    # ---------- 属性覆盖选项 ----------
    def copy_attributes_to_options(self, entries):
        last_non_option = None
        for entry in entries:
            if entry.get("is_chapter"):
                continue
            if entry.get("co"):
                if last_non_option is not None:
                    for key in ["background", "cg", "sd"]:
                        val = last_non_option.get(key, "")
                        entry[key] = val
            else:
                last_non_option = entry

    # ---------- 转换线程 ----------
    def convert_script_thread(self):
        try:
            if self.imported_files:
                if self.merge_var.get() == 1:
                    # 合并模式
                    self.queue.put(("progress_update", {"progress": 0, "message": "分别转换文件中（准备合并）..."}))
                    all_entries = []
                    offset = 0
                    total_files = len(self.imported_files)
                    scene_items = []

                    for idx, fp in enumerate(self.imported_files):
                        if self.cancel_processing:
                            break
                        with open(fp, 'r', encoding='utf-8-sig') as f:
                            content = f.read()
                        raw_entries, label_to_id, scene_meta = self.parse_script_with_options(content)

                        if self.cancel_processing:
                            break

                        # 转换选项标签
                        for entry in raw_entries:
                            if entry.get("co"):
                                for key in ["c1t", "c2t", "c3t", "c4t", "c5t"]:
                                    target_label = entry.get(key, "")
                                    if target_label:
                                        if target_label in label_to_id:
                                            entry[key] = label_to_id[target_label]
                                        elif target_label.lstrip('*') in label_to_id:
                                            entry[key] = label_to_id[target_label.lstrip('*')]
                                        else:
                                            entry[key] = 0
                                            self.queue.put(("status_update", f"文件 {os.path.basename(fp)} 中目标标签 '{target_label}' 未映射，已置为0"))
                                    else:
                                        entry[key] = 0

                        self.process_characters(raw_entries)

                        # 加偏移
                        file_entries = []
                        for entry in raw_entries:
                            new_entry = dict(entry)
                            if new_entry.get("co"):
                                for opt_key in ["c1t", "c2t", "c3t", "c4t", "c5t"]:
                                    if opt_key in new_entry and isinstance(new_entry[opt_key], int) and new_entry[opt_key] > 0:
                                        new_entry[opt_key] += offset
                            file_entries.append(new_entry)

                        all_entries.extend(file_entries)

                        for label, meta in scene_meta.items():
                            start = meta["start"] + offset
                            end = meta["end"] + offset
                            next_ids = []
                            for lbl in meta["nexts"]:
                                if lbl in label_to_id:
                                    next_ids.append(label_to_id[lbl] + offset)
                                elif lbl.lstrip('*') in label_to_id:
                                    next_ids.append(label_to_id[lbl.lstrip('*')] + offset)
                            scene_items.append({
                                "start": start,
                                "end": end,
                                "nexts": next_ids
                            })

                        offset += len(raw_entries)

                        self.queue.put(("progress_update", {
                            "progress": (idx + 1) / total_files * 100,
                            "message": f"处理 {os.path.basename(fp)}（累计 {offset} 条）"
                        }))

                    if self.cancel_processing:
                        return

                    all_entries = self.deduplicate_adjacent_option_pages(all_entries)
                    self.copy_attributes_to_options(all_entries)

                    # 生成最终JSON
                    result = {}
                    for i, item in enumerate(all_entries, start=1):
                        out = {}
                        if item.get("is_chapter"):
                            out["b"] = "ecall"
                            out["s"] = item.get("speaker", "[CHAPTER]")  # 添加 s 字段
                        else:
                            if item.get("background"):
                                out["b"] = item["background"]
                            if item.get("speaker"):
                                out["s"] = item["speaker"]
                            if item.get("text"):
                                out["t"] = item["text"]
                            if item.get("characters"):
                                out["c"] = item["characters"]
                            if item.get("blur"):
                                out["z"] = 2
                            if item.get("cg"):
                                out["cg"] = item["cg"]
                            if item.get("sd"):
                                out["sd"] = item["sd"]
                            if item.get("co"):
                                out["co"] = True
                                for opt_idx in range(1, 6):
                                    opt_key = f"c{opt_idx}"
                                    if item.get(opt_key):
                                        out[opt_key] = item[opt_key]
                                        out[f"{opt_key}t"] = item.get(f"{opt_key}t", 0)
                        if out:
                            result[str(i)] = out

                    output_str = json.dumps(result, ensure_ascii=False, indent=2)
                    self.queue.put(("output_text", output_str))
                    self.queue.put(("status_update", f"合并完成，共 {len(all_entries)} 个条目"))

                    # 保存场景元数据
                    start_set = {item["start"] for item in scene_items}
                    sorted_starts = sorted(start_set)
                    new_scene_items = []
                    for idx, start in enumerate(sorted_starts):
                        if idx + 1 < len(sorted_starts):
                            end = sorted_starts[idx+1] - 1
                        else:
                            end = len(all_entries)
                        nexts = []
                        for item in scene_items:
                            if item["start"] == start:
                                nexts = item["nexts"]
                                break
                        new_scene_items.append({"start": start, "end": end, "nexts": nexts})
                    self.scene_meta_by_start = {}
                    for item in new_scene_items:
                        self.scene_meta_by_start[item["start"]] = (item["end"], item["nexts"])

                else:
                    # 分别转换模式
                    self.queue.put(("progress_update", {"progress": 0, "message": "分别转换文件中..."}))
                    all_outputs = []
                    total_files = len(self.imported_files)
                    self.scene_meta_by_start = {}

                    for idx, fp in enumerate(self.imported_files):
                        if self.cancel_processing:
                            break
                        with open(fp, 'r', encoding='utf-8-sig') as f:
                            content = f.read()
                        entries, label_to_id, scene_meta = self.parse_script_with_options(content)

                        if self.cancel_processing:
                            break

                        for entry in entries:
                            if entry.get("co"):
                                for key in ["c1t", "c2t", "c3t", "c4t", "c5t"]:
                                    target_label = entry.get(key, "")
                                    if target_label:
                                        if target_label in label_to_id:
                                            entry[key] = label_to_id[target_label]
                                        elif target_label.lstrip('*') in label_to_id:
                                            entry[key] = label_to_id[target_label.lstrip('*')]
                                        else:
                                            entry[key] = 0
                                            self.queue.put(("status_update", f"文件 {os.path.basename(fp)} 中目标标签 '{target_label}' 未映射，已置为0"))
                                    else:
                                        entry[key] = 0

                        self.process_characters(entries)
                        entries = self.deduplicate_adjacent_option_pages(entries)
                        self.copy_attributes_to_options(entries)

                        result = {}
                        for i, item in enumerate(entries, start=1):
                            out = {}
                            if item.get("is_chapter"):
                                out["b"] = "ecall"
                                out["s"] = item.get("speaker", "[CHAPTER]")
                            else:
                                if item.get("background"):
                                    out["b"] = item["background"]
                                if item.get("speaker"):
                                    out["s"] = item["speaker"]
                                if item.get("text"):
                                    out["t"] = item["text"]
                                if item.get("characters"):
                                    out["c"] = item["characters"]
                                if item.get("blur"):
                                    out["z"] = 2
                                if item.get("cg"):
                                    out["cg"] = item["cg"]
                                if item.get("sd"):
                                    out["sd"] = item["sd"]
                                if item.get("co"):
                                    out["co"] = True
                                    for opt_idx in range(1, 6):
                                        opt_key = f"c{opt_idx}"
                                        if item.get(opt_key):
                                            out[opt_key] = item[opt_key]
                                            out[f"{opt_key}t"] = item.get(f"{opt_key}t", 0)
                            if out:
                                result[str(i)] = out

                        output_str = json.dumps(result, ensure_ascii=False, indent=2)
                        header = f"# ========== {os.path.basename(fp)} ==========\n"
                        all_outputs.append(header + output_str)

                        for label, meta in scene_meta.items():
                            start = meta["start"]
                            end = meta["end"]
                            next_ids = []
                            for lbl in meta["nexts"]:
                                if lbl in label_to_id:
                                    next_ids.append(label_to_id[lbl])
                                elif lbl.lstrip('*') in label_to_id:
                                    next_ids.append(label_to_id[lbl.lstrip('*')])
                            self.scene_meta_by_start[start] = (end, next_ids)

                        self.queue.put(("progress_update", {
                            "progress": (idx + 1) / total_files * 100,
                            "message": f"完成 {os.path.basename(fp)}"
                        }))

                    if self.cancel_processing:
                        return
                    combined = "\n\n".join(all_outputs)
                    self.queue.put(("output_text", combined))
                    self.queue.put(("status_update", f"分别转换完成，共 {len(self.imported_files)} 个文件"))

            else:
                # 单文件或手动输入
                input_data = self.input_text.get("1.0", tk.END).strip()
                if not input_data:
                    self.queue.put(("output_text", "请输入数据"))
                    self.queue.put(("processing_done", None))
                    return
                entries, label_to_id, scene_meta = self.parse_script_with_options(input_data)
                if not entries:
                    self.queue.put(("status_update", "未检测到 scenes 结构，无法提取选项"))
                self.queue.put(("status_update", f"提取到 {len(entries)} 个条目"))

                if self.cancel_processing:
                    return
                if not entries:
                    self.queue.put(("status_update", "警告: 未找到有效条目"))
                    self.queue.put(("output_text", "（无有效条目）"))
                    self.queue.put(("processing_done", None))
                    return

                for entry in entries:
                    if entry.get("co"):
                        for key in ["c1t", "c2t", "c3t", "c4t", "c5t"]:
                            target_label = entry.get(key, "")
                            if target_label:
                                if target_label in label_to_id:
                                    entry[key] = label_to_id[target_label]
                                elif target_label.lstrip('*') in label_to_id:
                                    entry[key] = label_to_id[target_label.lstrip('*')]
                                else:
                                    entry[key] = 0
                                    self.queue.put(("status_update", f"警告: 目标标签 '{target_label}' 未映射，已置为0"))
                            else:
                                entry[key] = 0

                self.process_characters(entries)
                entries = self.deduplicate_adjacent_option_pages(entries)
                self.copy_attributes_to_options(entries)

                result = {}
                for i, item in enumerate(entries, start=1):
                    out = {}
                    if item.get("is_chapter"):
                        out["b"] = "ecall"
                        out["s"] = item.get("speaker", "[CHAPTER]")
                    else:
                        if item.get("background"):
                            out["b"] = item["background"]
                        if item.get("speaker"):
                            out["s"] = item["speaker"]
                        if item.get("text"):
                            out["t"] = item["text"]
                        if item.get("characters"):
                            out["c"] = item["characters"]
                        if item.get("blur"):
                            out["z"] = 2
                        if item.get("cg"):
                            out["cg"] = item["cg"]
                        if item.get("sd"):
                            out["sd"] = item["sd"]
                        if item.get("co"):
                            out["co"] = True
                            for opt_idx in range(1, 6):
                                opt_key = f"c{opt_idx}"
                                if item.get(opt_key):
                                    out[opt_key] = item[opt_key]
                                    out[f"{opt_key}t"] = item.get(f"{opt_key}t", 0)
                    if out:
                        result[str(i)] = out

                output_str = json.dumps(result, ensure_ascii=False, indent=2)
                self.queue.put(("output_text", output_str))
                self.queue.put(("status_update", f"完成，共 {len(entries)} 个条目"))

                # 保存场景元数据
                scene_by_start = {}
                for label, meta in scene_meta.items():
                    start = meta["start"]
                    end = meta["end"]
                    next_ids = []
                    for lbl in meta["nexts"]:
                        if lbl in label_to_id:
                            next_ids.append(label_to_id[lbl])
                        elif lbl.lstrip('*') in label_to_id:
                            next_ids.append(label_to_id[lbl.lstrip('*')])
                    scene_by_start[start] = (end, next_ids)
                self.scene_meta_by_start = scene_by_start

            self.queue.put(("processing_done", None))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.queue.put(("processing_error", f"转换错误: {e}"))

    # ---------- 加载示例 ----------
    def load_example(self):
        example = '''{
  "scenes": [
    {
      "label": "*com_part_1",
      "lines": [["chapter","1-1","true","hide","true"]],
      "texts": [
        ["将臣", null, [
          [null, "「………」"],
          [null, "......"],
          [null, "「……」"]
        ], null, 192, {"data": []}]
      ]
    },
    {
      "label": "*com_part_1_sel",
      "lines": [],
      "selects": [
        {
          "exp": "SetBranchFlags(\\"s001*com_part_1_sel\\",1)",
          "language": [null, {"text":"Tell her the truth"}, {"text":"说实话"}, {"text":"說實話"}],
          "render": 1,
          "selidx": 0,
          "storage": "001・アーサー王ver1.07.ks",
          "tag": "s001*com_part_1_sel:1",
          "target": "*001_01A",
          "text": "正直に言う"
        },
        {
          "exp": "SetBranchFlags(\\"s001*com_part_1_sel\\",2)",
          "language": [null, {"text":"Dodge the question"}, {"text":"敷衍过去"}, {"text":"敷衍過去"}],
          "render": 1,
          "selidx": 1,
          "storage": "001・アーサー王ver1.07.ks",
          "tag": "s001*com_part_1_sel:2",
          "target": "*001_01B",
          "text": "誤魔化す"
        }
      ]
    },
    {
      "label": "*001_01A",
      "lines": [],
      "texts": [
        ["将臣", null, [
          [null, "「正直、見惚れてた」"],
          [null, "Honestly? Yeah, it did."],
          [null, "「说实话，我确实是看入迷了」"],
          [null, "「实话实说，看入迷了」"]
        ], null, 1744, {"data": []}]
      ],
      "nexts": [{"target": "*dummy3"}]
    },
    {
      "label": "*001_01B",
      "lines": [],
      "texts": [
        ["将臣", null, [
          [null, "「目の下にゴミが――」"],
          [null, "There's something stuck under your eye."],
          [null, "「你眼睛下面沾了沙子」"],
          [null, "「眼睛下面有脏东西――」"]
        ], null, 1744, {"data": []}]
      ],
      "nexts": [{"target": "*dummy3"}]
    },
    {
      "label": "*dummy3",
      "lines": [],
      "texts": [],
      "nexts": [{"target": "*001_01com"}]
    },
    {
      "label": "*001_01com",
      "lines": [],
      "texts": [
        ["将臣", null, [
          [null, "「あ、はい？」"],
          [null, "Oh, yes?"],
          [null, "「啊，怎么了？」"],
          [null, "「啊，嗯？」"]
        ], null, 1744, {"data": []}]
      ]
    }
  ]
}'''
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", example)
        self.imported_files = []
        self.file_info_var.set("示例（含选项和合流）")
        self.status_var.set("已加载含选项和合流示例，点击“转换”测试选项提取")

def main():
    root = tk.Tk()
    app = GalgameScriptConverter(root)
    root.mainloop()

if __name__ == "__main__":
    main()