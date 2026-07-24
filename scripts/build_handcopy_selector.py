#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSET_MANIFEST = ROOT / "references" / "style_example_assets.json"
CONFIG_FIELDS = {
    "recommend",
    "age_band",
    "language",
    "paper_size",
    "orientation",
}
LAYOUT_NAMES = {
    "curved_narrative": "曲线叙事型",
    "central_growth": "中心生长型",
    "scene_journey": "场景漫游型",
    "spiral_exploration": "螺旋探索型",
    "contrast_bridge": "对比桥梁型",
    "seasonal_wreath": "四季/阶段花环型",
    "stair_step_progress": "阶梯递进型",
    "open_book_map": "翻开书页型",
    "question_answer_path": "问答路径型",
    "loose_mind_map": "松散思维导图型",
    "cause_effect_ripple": "因果涟漪型",
}
AGE_BANDS = ("小学低年级", "小学高年级", "初中", "高中")
LANGUAGES = {
    "zh": "中文版",
    "en": "英文版",
    "zh_and_en": "中英分别生成",
}
PAPER_SIZES = {
    "A3": "A3 · 420×297 mm",
    "A4": "A4 · 297×210 mm",
    "8K": "8K · 默认 390×270 mm",
}
ORIENTATIONS = {
    "landscape": "横版",
    "portrait": "竖版",
}
TRACING_TEXT_MODES = {
    "gray_all_text": "灰度全部文字",
    "title_only": "只带主标题",
    "title_and_subtitles": "带主标题和小标题",
    "blank_structure": "完全无文字",
}
DISALLOWED_HANDCOPY_STYLES = {
    "isometric_timeline_miniature",
    "miniature_map_life_scene",
    "miniature_checklist_scene",
    "fabric_micro_scene_ad",
    "childlike_cultural_infographic",
    "expressive_3d_quirky_character",
    "cute_3d_plastic_icon",
    "candy_glass_3d_icon",
    "circular_3d_texture_icon",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 cc2image 学生手抄报方案选择器")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stdin-config", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def validate_config(payload: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) != CONFIG_FIELDS:
        raise ValueError("stdin 配置字段无效")
    recommendations = payload["recommend"]
    if not isinstance(recommendations, list) or len(recommendations) != 3:
        raise ValueError("recommend 必须恰好包含三套方案")
    required = {"layout_id", "style_id", "title", "reason"}
    for item in recommendations:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("recommend 方案字段无效")
        if not all(isinstance(item[field], str) and item[field].strip() for field in required):
            raise ValueError("recommend 方案字段必须为非空字符串")
        if item["layout_id"] not in LAYOUT_NAMES:
            raise ValueError(f"未知 layout_id: {item['layout_id']}")
        if len(item["title"]) > 32 or len(item["reason"]) > 80:
            raise ValueError("方案标题或理由过长")
    layout_ids = [item["layout_id"] for item in recommendations]
    if len(set(layout_ids)) != 3:
        raise ValueError("三套 layout_id 不能重复")
    style_ids = [item["style_id"] for item in recommendations]
    if len(set(style_ids)) != 3:
        raise ValueError("三套 style_id 不能重复")
    disallowed = sorted(set(style_ids) & DISALLOWED_HANDCOPY_STYLES)
    if disallowed:
        raise ValueError(f"学生手抄报禁用复杂风格: {', '.join(disallowed)}")
    allowed_fields = {
        "age_band": AGE_BANDS,
        "language": LANGUAGES,
        "paper_size": PAPER_SIZES,
        "orientation": ORIENTATIONS,
    }
    for field, allowed in allowed_fields.items():
        if payload[field] not in allowed:
            raise ValueError(f"{field} 取值无效: {payload[field]}")
    for style_id in style_ids:
        asset_path(style_id)
    return payload


def load_assets() -> dict:
    return json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))["styles"]


def asset_path(style_id: str) -> Path:
    assets = load_assets()
    if style_id not in assets:
        raise ValueError(f"缺少示例图映射: {style_id}")
    path = (ROOT / assets[style_id]["thumbnail"]).resolve()
    if ROOT not in path.parents or not path.is_file():
        raise ValueError(f"缩略图路径无效: {path}")
    if path.read_bytes()[:3] != b"\xff\xd8\xff":
        raise ValueError(f"缩略图不是 JPEG: {path}")
    return path


def image_data(style_id: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(
        asset_path(style_id).read_bytes()
    ).decode()


def select_options(values: dict[str, str], selected: str) -> str:
    return "\n".join(
        f'<option value="{html.escape(value)}"{" selected" if value == selected else ""}>{html.escape(label)}</option>'
        for value, label in values.items()
    )


def layout_options(selected: str) -> str:
    return select_options(LAYOUT_NAMES, selected)


def build_fragment(payload: dict) -> str:
    payload = validate_config(payload)
    cards = []
    for index, item in enumerate(payload["recommend"]):
        cards.append(
            f'''<button type="button" class="card concept-card" data-layout-id="{html.escape(item["layout_id"])}" data-style-id="{html.escape(item["style_id"])}" aria-pressed="{'true' if index == 0 else 'false'}">
  <img src="{image_data(item["style_id"])}" alt="{html.escape(item["title"])}视觉参考">
  <span class="concept-copy">
    <span class="text-small">{html.escape(LAYOUT_NAMES[item["layout_id"]])}</span>
    <strong>{html.escape(item["title"])}</strong>
    <span class="text-small">{html.escape(item["reason"])}</span>
  </span>
</button>'''
        )
    selected = payload["recommend"][0]
    config_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    return f'''<div id="cc2image-handcopy-selector">
<style>
  #cc2image-handcopy-selector {{ display: grid; gap: 18px; color: var(--foreground); }}
  #cc2image-handcopy-selector .concepts {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  #cc2image-handcopy-selector .concept-card {{ display: grid; gap: 10px; overflow: hidden; width: 100%; text-align: left; }}
  #cc2image-handcopy-selector .concept-card img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; border-radius: inherit; }}
  #cc2image-handcopy-selector .concept-copy {{ display: grid; gap: 5px; }}
  #cc2image-handcopy-selector .concept-card[aria-pressed="true"] {{ border-color: color-mix(in oklab, var(--primary) 64%, var(--border) 36%); box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--primary) 46%, transparent); }}
  #cc2image-handcopy-selector .fields {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
  #cc2image-handcopy-selector .field {{ display: grid; gap: 7px; }}
  #cc2image-handcopy-selector .summary {{ margin: 0; color: var(--muted-foreground); }}
  #cc2image-handcopy-selector .status {{ min-height: 1.4em; margin: 0; }}
  @media (max-width: 620px) {{
    #cc2image-handcopy-selector .concepts,
    #cc2image-handcopy-selector .fields {{ grid-template-columns: 1fr; }}
  }}
</style>

<section aria-labelledby="handcopy-concepts-heading">
  <h3 id="handcopy-concepts-heading">选择手抄报呈现思路</h3>
  <p class="summary">文字与思路优先：像一页可手绘的特殊幻灯片，图画只用于解释和连接。绘画部分约 20 分钟可临摹，最多 1 个主图和 3 个小图。</p>
  <div class="viz-grid concepts">
{chr(10).join(cards)}
  </div>
</section>

<section class="fields" aria-label="手抄报参数">
  <label class="field">学生年龄
    <select id="handcopy-age" class="form-select">
      {select_options({value: value for value in AGE_BANDS}, payload["age_band"])}
    </select>
  </label>
  <label class="field">语言
    <select id="handcopy-language" class="form-select">
      {select_options(LANGUAGES, payload["language"])}
    </select>
  </label>
  <label class="field">纸张尺寸
    <select id="handcopy-paper" class="form-select">
      {select_options(PAPER_SIZES, payload["paper_size"])}
    </select>
  </label>
  <label class="field">方向
    <select id="handcopy-orientation" class="form-select">
      {select_options(ORIENTATIONS, payload["orientation"])}
    </select>
  </label>
  <label class="field">更多手抄报结构
    <select id="handcopy-layout" class="form-select">
      {layout_options(selected["layout_id"])}
    </select>
  </label>
  <label class="field">线稿文字保留
    <select id="handcopy-tracing-text" class="form-select">
      {select_options(TRACING_TEXT_MODES, "blank_structure")}
    </select>
  </label>
</section>

<p class="summary">固定产物：彩绘完成版 + 线条临摹参考版</p>
<p class="summary">线稿统一使用浅灰色线条，可选择灰度全部文字、只带主标题、带主标题和小标题，或完全无文字。</p>
<p id="handcopy-summary" class="summary"></p>
<button id="handcopy-submit" type="button" class="btn btn-primary btn-block">使用此方案继续</button>
<p id="handcopy-status" class="status text-small text-destructive" role="status" aria-live="polite"></p>

<script>
(() => {{
  const root = document.getElementById('cc2image-handcopy-selector');
  const initial = {config_json};
  const cards = [...root.querySelectorAll('[data-layout-id]')];
  const age = root.querySelector('#handcopy-age');
  const language = root.querySelector('#handcopy-language');
  const paper = root.querySelector('#handcopy-paper');
  const orientation = root.querySelector('#handcopy-orientation');
  const layout = root.querySelector('#handcopy-layout');
  const tracingText = root.querySelector('#handcopy-tracing-text');
  const summary = root.querySelector('#handcopy-summary');
  const submit = root.querySelector('#handcopy-submit');
  const status = root.querySelector('#handcopy-status');
  let selectedLayout = {json.dumps(selected["layout_id"], ensure_ascii=False)};
  let selectedStyle = {json.dumps(selected["style_id"], ensure_ascii=False)};
  let selectedTitle = {json.dumps(selected["title"], ensure_ascii=False)};

  const update = () => {{
    cards.forEach(card => card.setAttribute('aria-pressed', String(card.dataset.layoutId === selectedLayout)));
    layout.value = selectedLayout;
    summary.textContent = `${{selectedTitle}} · ${{layout.options[layout.selectedIndex].text}} · ${{tracingText.options[tracingText.selectedIndex].text}} · ${{age.value}} · ${{language.options[language.selectedIndex].text}} · ${{paper.value}} · ${{orientation.options[orientation.selectedIndex].text}}`;
  }};
  cards.forEach(card => card.addEventListener('click', () => {{
    selectedLayout = card.dataset.layoutId;
    selectedStyle = card.dataset.styleId;
    selectedTitle = card.querySelector('strong').textContent;
    update();
  }}));
  layout.addEventListener('change', () => {{
    selectedLayout = layout.value;
    selectedTitle = layout.options[layout.selectedIndex].text;
    update();
  }});
  [age, language, paper, orientation, tracingText].forEach(control => control.addEventListener('change', update));
  submit.addEventListener('click', async () => {{
    const prompt = `继续当前 cc2image 学生手抄报任务，不要再次打开选择器。\nCC2IMAGE_HANDCOPY_SELECTION_V1\nlayout_id=${{selectedLayout}}\nstyle_id=${{selectedStyle}}\nage_band=${{age.value}}\nlanguage=${{language.value}}\npaper_size=${{paper.value}}\norientation=${{orientation.value}}\ntracing_text_mode=${{tracingText.value}}\noutputs=colored_and_tracing\nskip_selector=true\nEND_CC2IMAGE_HANDCOPY_SELECTION`;
    submit.disabled = true;
    submit.textContent = '正在提交…';
    status.textContent = '';
    try {{
      await window.openai.sendFollowUpMessage({{ title: '确认学生手抄报方案', prompt }});
    }} catch (error) {{
      submit.disabled = false;
      submit.textContent = '使用此方案继续';
      status.textContent = '提交失败，请稍后重试。';
    }}
  }});
  update();
}})();
</script>
</div>
'''


def write_fragment(args: argparse.Namespace, restrict_output: bool = True) -> Path:
    if args.output_dir is not None:
        directory = args.output_dir.expanduser().resolve()
        output = directory / f"cc2image-handcopy-selector-{time.time_ns()}.html"
    elif args.output is not None:
        output = args.output.expanduser()
        if not output.is_absolute():
            raise ValueError("--output 必须为绝对路径")
        directory = output.parent.resolve()
    else:
        raise ValueError("缺少 --output 或 --output-dir")
    if restrict_output:
        visualization_root = (Path.home() / ".codex" / "visualizations").resolve()
        if directory != visualization_root and visualization_root not in directory.parents:
            raise ValueError("输出必须位于 Codex visualization 目录")
    if output.exists() or output.is_symlink():
        raise ValueError(f"输出文件已存在: {output}")
    fragment = build_fragment(args.config)
    if fragment.count("<img ") != 3 or fragment.count("data:image/jpeg;base64,") != 3:
        raise ValueError("推荐示例图必须恰好为 3 张")
    if len(fragment.encode()) >= 2_000_000:
        raise ValueError("fragment 超过 2 MB")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(fragment)
    return output


def example_config() -> dict:
    return {
        "recommend": [
            {
                "layout_id": "curved_narrative",
                "style_id": "minimal_line_art",
                "title": "曲线时间线",
                "reason": "用一条曲线和四个节点讲清阶段",
            },
            {
                "layout_id": "central_growth",
                "style_id": "handdrawn_knowledge_card",
                "title": "中心思维图",
                "reason": "从一个简笔符号向外展开知识点",
            },
            {
                "layout_id": "scene_journey",
                "style_id": "editorial_line_character",
                "title": "路径讲解图",
                "reason": "用简化路线、编号和关键词引导阅读",
            },
        ],
        "age_band": "初中",
        "language": "zh",
        "paper_size": "A3",
        "orientation": "landscape",
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        args = argparse.Namespace(
            output=None,
            output_dir=Path(directory),
            config=example_config(),
            self_test=True,
        )
        first = write_fragment(args, restrict_output=False)
        second = write_fragment(args, restrict_output=False)
        text = first.read_text(encoding="utf-8")
        assert first != second
        assert text.count("<img ") == 3
        assert text.count("data:image/jpeg;base64,") == 3
        assert "CC2IMAGE_HANDCOPY_SELECTION_V1" in text
        assert "colored_and_tracing" in text
        assert "文字与思路优先" in text
        assert "约 20 分钟" in text
        assert "更多手抄报结构" in text
        assert "线稿文字保留" in text
        assert "浅灰色线条" in text
        assert "tracing_text_mode=" in text
        assert "\ntext_mode=" not in text
        assert first.stat().st_size < 2_000_000


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    if not args.stdin_config:
        raise ValueError("必须使用 --stdin-config 或 --self-test")
    args.config = validate_config(json.loads(sys.stdin.readline()))
    output = write_fragment(args)
    print(json.dumps({"file": output.name}, ensure_ascii=False))


if __name__ == "__main__":
    main()
