import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def click_commands(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    commands = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != "command" or not decorator.args:
                continue
            value = decorator.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                commands.add(value.value)
    return commands


class NativeCliSurfaceTest(unittest.TestCase):
    def test_config_commands_are_registered(self):
        module = ROOT / "src/sonic-utilities/config/personaforge.py"
        self.assertEqual(click_commands(module), {"apply", "persist", "deactivate"})
        main = (ROOT / "src/sonic-utilities/config/main.py").read_text(encoding="utf-8")
        self.assertIn("config.add_command(personaforge.personaforge)", main)

    def test_show_commands_are_registered(self):
        module = ROOT / "src/sonic-utilities/show/personaforge.py"
        self.assertEqual(click_commands(module), {"status", "plan", "drift"})
        main = (ROOT / "src/sonic-utilities/show/main.py").read_text(encoding="utf-8")
        self.assertIn("cli.add_command(personaforge.personaforge)", main)

    def test_runtime_wheel_is_an_image_dependency(self):
        setup = (ROOT / "src/sonic-utilities/setup.py").read_text(encoding="utf-8")
        rules = (ROOT / "rules/sonic-utilities.mk").read_text(encoding="utf-8")
        slave = (ROOT / "slave.mk").read_text(encoding="utf-8")
        image_template = (ROOT / "files/build_templates/sonic_debian_extension.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("sonic-personaforge>=0.1.0", setup)
        self.assertIn("$(SONIC_PERSONAFORGE)", rules)
        self.assertIn('sonic_personaforge_wheel_path="$(addprefix $(PYTHON_WHEELS_PATH)/,$(SONIC_PERSONAFORGE))"', slave)
        self.assertLess(
            image_template.index("install_pip_package {{sonic_personaforge_wheel_path}}"),
            image_template.index("install_pip_package {{sonic_utilities_py3_wheel_path}}"),
        )


if __name__ == "__main__":
    unittest.main()
