import argparse
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_handcopy_selector.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_handcopy_selector", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HandcopySelectorTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.payload = {
            "recommend": [
                {
                    "layout_id": "curved_narrative",
                    "style_id": "minimal_line_art",
                    "title": "河流时间线",
                    "reason": "沿弯曲河流讲清四个阶段",
                },
                {
                    "layout_id": "central_growth",
                    "style_id": "handdrawn_knowledge_card",
                    "title": "中心主图生长",
                    "reason": "从核心文物向外延伸知识点",
                },
                {
                    "layout_id": "scene_journey",
                    "style_id": "editorial_line_character",
                    "title": "场景漫游",
                    "reason": "在连续场景中边走边读",
                },
            ],
            "age_band": "初中",
            "language": "zh",
            "paper_size": "A3",
            "orientation": "landscape",
        }

    def args(self):
        return argparse.Namespace(
            output=None,
            output_dir=None,
            config=self.payload,
            self_test=False,
        )

    def test_rejects_missing_or_extra_stdin_fields(self):
        missing = dict(self.payload)
        missing.pop("language")
        with self.assertRaisesRegex(ValueError, "stdin 配置字段无效"):
            self.module.validate_config(missing)
        extra = dict(self.payload, topic="不应进入选择器")
        with self.assertRaisesRegex(ValueError, "stdin 配置字段无效"):
            self.module.validate_config(extra)

    def test_rejects_duplicate_or_unknown_layouts(self):
        duplicate = json.loads(json.dumps(self.payload, ensure_ascii=False))
        duplicate["recommend"][1]["layout_id"] = "curved_narrative"
        with self.assertRaisesRegex(ValueError, "三套 layout_id 不能重复"):
            self.module.validate_config(duplicate)
        unknown = json.loads(json.dumps(self.payload, ensure_ascii=False))
        unknown["recommend"][0]["layout_id"] = "grid_cards"
        with self.assertRaisesRegex(ValueError, "未知 layout_id"):
            self.module.validate_config(unknown)

    def test_rejects_invalid_controls(self):
        cases = [
            ("age_band", "幼儿园"),
            ("language", "fr"),
            ("paper_size", "Letter"),
            ("orientation", "square"),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                payload = dict(self.payload)
                payload[field] = value
                with self.assertRaises(ValueError):
                    self.module.validate_config(payload)

    def test_fragment_has_three_examples_and_all_controls(self):
        fragment = self.module.build_fragment(self.payload)
        self.assertEqual(fragment.count("<img "), 3)
        self.assertEqual(fragment.count("data:image/jpeg;base64,"), 3)
        for text in [
            "学生年龄",
            "中文",
            "英文",
            "中英分别生成",
            "A3",
            "A4",
            "8K",
            "横版",
            "竖版",
            "CC2IMAGE_HANDCOPY_SELECTION_V1",
            "colored_and_tracing",
            "文字与思路优先",
            "约 20 分钟",
            "最多 1 个主图和 3 个小图",
            "更多手抄报结构",
            "螺旋探索型",
            "对比桥梁型",
            "四季/阶段花环型",
            "线稿文字保留",
            "选择线稿文字保留方式",
            "灰度全部文字",
            "只带主标题",
            "带主标题和小标题",
            "完全无文字",
            "浅灰色线条",
            "tracing_text_mode=",
        ]:
            self.assertIn(text, fragment)
        self.assertIn('class="tracing-panel"', fragment)
        self.assertEqual(
            len(re.findall(r'<input type="radio" name="tracing-text-mode"', fragment)),
            4,
        )
        self.assertIn('value="blank_structure" checked', fragment)
        self.assertNotIn("handcopy-tracing-text", fragment)
        self.assertNotIn("线稿文字区", fragment)
        self.assertNotIn("\ntext_mode=", fragment)
        self.assertNotIn("保留范文", fragment)
        self.assertLess(len(fragment.encode()), 2_000_000)

    def test_more_layouts_and_tracing_modes_are_validated(self):
        self.assertIn("spiral_exploration", self.module.LAYOUT_NAMES)
        self.assertIn("contrast_bridge", self.module.LAYOUT_NAMES)
        self.assertEqual(
            set(self.module.TRACING_TEXT_MODES),
            {
                "gray_all_text",
                "title_only",
                "title_and_subtitles",
                "blank_structure",
            },
        )

    def test_rejects_styles_that_induce_complex_student_posters(self):
        for style_id in [
            "isometric_timeline_miniature",
            "miniature_map_life_scene",
            "childlike_cultural_infographic",
            "expressive_3d_quirky_character",
        ]:
            with self.subTest(style_id=style_id):
                payload = json.loads(json.dumps(self.payload, ensure_ascii=False))
                payload["recommend"][0]["style_id"] = style_id
                with self.assertRaisesRegex(ValueError, "学生手抄报禁用复杂风格"):
                    self.module.validate_config(payload)

    def test_recommended_assets_are_existing_jpegs(self):
        for item in self.payload["recommend"]:
            path = self.module.asset_path(item["style_id"])
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes()[:3], b"\xff\xd8\xff")

    def test_unique_output_names(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args()
            args.output_dir = Path(directory)
            first = self.module.write_fragment(args, restrict_output=False)
            second = self.module.write_fragment(args, restrict_output=False)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    def test_default_output_restriction_rejects_other_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args()
            args.output_dir = Path(directory)
            with self.assertRaisesRegex(ValueError, "Codex visualization"):
                self.module.write_fragment(args)


if __name__ == "__main__":
    unittest.main()
