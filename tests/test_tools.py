
from chat_csa.agent.prompt import build_system_prompt
from chat_csa.agent.tools import bash, edit, read, write


def test_write_read_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert "Wrote" in write.invoke({"path": "hello.txt", "content": "world"})
    assert "world" in read.invoke({"path": "hello.txt"})
    assert "Edited" in edit.invoke({"path": "hello.txt", "oldText": "world", "newText": "earth"})
    assert "earth" in read.invoke({"path": "hello.txt"})


def test_bash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = bash.invoke({"command": "echo hi"})
    assert "hi" in out


def test_prompt_build(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Test agents")
    skills = tmp_path / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# Demo skill")
    prompt = build_system_prompt(tmp_path)
    assert "Test agents" in prompt
    assert "Demo skill" in prompt
