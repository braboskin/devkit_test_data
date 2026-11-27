import pathlib, re
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\chat\ui\Chat.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace("  DocumentItem,\n", "", 1)
s = s.replace("  SwitchField,\n", "", 1)
s = s.replace("""/** Чип-действие: вставляет маркер «@» в текст, чтобы упомянуть
                 * документы словами (контекст выбирается скрепкой рядом).
                 * Чип проекта скрыт: у чата сейчас нет проекта в контракте
                 * (`Chat` без `project_id`) — появится, когда API его отдаст.
                 */""", "")
s = s.replace('              type="button"\n              variant="primary"\n              disabled={agentId === null || actions.busy}', '              variant="primary"\n              disabled={agentId === null || actions.busy}')
# remove unused styled blocks by exact block boundaries
def drop_block(text, start_marker):
    idx = text.find(start_marker)
    if idx < 0:
        return text, False
    end = text.find("\n`;\n", idx)
    if end < 0:
        return text, False
    return text[:idx] + text[end + len("\n`;\n"):], True

for marker in ("const ChipButton = styled.button`", "const DocsPanel = styled.div`"):
    s, ok = drop_block(s, marker)
    print(marker.split()[1], "removed:", ok)
p.write_text(s, encoding="utf-8")
print("cleanup done")
